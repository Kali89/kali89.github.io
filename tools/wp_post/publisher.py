"""Plan and apply a sync of one Markdown file to one WordPress post.

Every operation runs in two phases:

1. plan()    uses a read-only client (GET requests only) to resolve the post,
             check the safety rules, detect conflicts and compute exactly what
             would change. Dry runs and `status` stop here.
2. execute() creates terms, uploads media, and sends one create or update request
             for the post. Then it records the new baseline locally.

Command semantics:

  sync     Create a new draft, or update an existing draft/pending post. It
           never touches a scheduled, published or private post, and it never
           changes status.
  publish  Make a post public for the first time: new or draft → publish, or
           future if the date is in the future. Asks for confirmation unless
           --yes. Refuses posts that are already public or scheduled.
  update   Update an existing post in place, keeping its status. Never creates.
           The only way to change a live post.
"""

from __future__ import annotations

import datetime as dt
import difflib
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from wp_post.client import WordPressClient
from wp_post.config import Config
from wp_post.document import DateValue, Post, load_post, record_wordpress_id
from wp_post.errors import (
    AbortedError,
    ConflictError,
    RefusedError,
    RemoteError,
    ValidationError,
)
from wp_post.media import MediaAction, MediaManifest, MediaPlanner, collect_images
from wp_post.render import MediaRef, has_block_delimiters, render, smarten
from wp_post.state import (
    SyncState,
    fingerprint,
    now_iso,
    payload_hash,
    raw,
)
from wp_post.terms import READER_TERM_LIMIT, TermPlan, TermResolver, combined_term_count
from wp_post.ui import Console

LIVE = {"publish", "private"}
NOT_YET_PUBLIC = {"draft", "pending"}


@dataclass
class Options:
    dry_run: bool = False
    force: bool = False
    yes: bool = False
    allow_many_terms: bool = False


@dataclass
class Conflict:
    kind: str  # "changed" | "no-baseline"
    fields: list[str]
    remote_modified: str
    baseline_modified: str | None
    diff: str

    def describe(self, edit_url: str) -> str:
        if self.kind == "no-baseline":
            head = (
                "this post exists in WordPress but has never been synced from this file, "
                "and its content differs from what this file would produce"
            )
        else:
            head = f"the remote post changed since the last sync: {', '.join(self.fields)}"
        lines = [
            head,
            f"  remote last modified: {self.remote_modified} UTC",
            f"  last synced version:  {self.baseline_modified or 'none recorded'}",
            f"  inspect: {edit_url} (Revisions panel shows who changed what)",
        ]
        return "\n".join(lines)


@dataclass
class Plan:
    command: str
    post: Post
    remote: dict[str, Any] | None
    resolved_by: str  # "wordpress_id" | "slug" | "new"
    target_status: str
    state: SyncState | None
    content: str
    media: list[MediaAction]
    featured: MediaAction | None
    tags: list[TermPlan] | None
    categories: list[TermPlan] | None
    desired: dict[str, Any]
    changed: list[str]
    conflict: Conflict | None
    term_count: int
    first_publication: bool
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def action(self) -> str:
        if self.remote is None:
            return "create"
        return "update" if self.changed else "noop"

    @property
    def post_id(self) -> int | None:
        return self.remote["id"] if self.remote else None


# -- dates ---------------------------------------------------------------------


def wp_date_fields(value: DateValue) -> dict[str, str]:
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            return {"date": value.replace(microsecond=0).isoformat()}
        utc = value.astimezone(dt.UTC).replace(tzinfo=None, microsecond=0)
        return {"date_gmt": utc.isoformat()}
    return {"date": f"{value.isoformat()}T00:00:00"}


def date_matches(value: DateValue, remote: dict[str, Any]) -> bool:
    fields = wp_date_fields(value)
    if "date_gmt" in fields:
        return (remote.get("date_gmt") or "") == fields["date_gmt"]
    if isinstance(value, dt.datetime):
        return (remote.get("date") or "") == fields["date"]
    return (remote.get("date") or "")[:10] == value.isoformat()


def to_utc(value: DateValue, gmt_offset_hours: float) -> dt.datetime:
    if isinstance(value, dt.datetime):
        if value.tzinfo is not None:
            return value.astimezone(dt.UTC)
        local = value
    else:
        local = dt.datetime.combine(value, dt.time())
    return (local - dt.timedelta(hours=gmt_offset_hours)).replace(tzinfo=dt.UTC)


def describe_date(post: Post) -> str:
    if post.date is None:
        return "none set: WordPress uses the moment of publication"
    return f"{post.date} (from {post.date_source})"


# -- planner -------------------------------------------------------------------


class Publisher:
    def __init__(
        self,
        repo_root: Path,
        config: Config,
        client: WordPressClient,
        console: Console | None = None,
        *,
        input_fn: Callable[[str], str] = input,
        isatty: Callable[[], bool] = lambda: sys.stdin.isatty(),
        now: Callable[[], dt.datetime] = lambda: dt.datetime.now(dt.UTC),
    ):
        self.repo_root = repo_root.resolve()
        self.config = config
        self.client = client
        self.console = console or Console()
        self.input_fn = input_fn
        self.isatty = isatty
        self.now = now
        self._gmt_offset: float | None = None

    def gmt_offset(self) -> float:
        if self._gmt_offset is None:
            root = self.client.get("/", auth=False) or {}
            self._gmt_offset = float(root.get("gmt_offset") or 0)
        return self._gmt_offset

    # resolution ---------------------------------------------------------------

    def _resolve(self, post: Post, ro: WordPressClient) -> tuple[dict[str, Any] | None, str]:
        if post.wordpress_id:
            try:
                remote = ro.get_post(post.wordpress_id)
            except RemoteError as exc:
                if getattr(exc, "wp_code", "") == "rest_post_invalid_id":
                    raise RefusedError(
                        f"{post.rel_path}: wordpress_id {post.wordpress_id} does not exist on "
                        f"{self.config.site_url}",
                        hint=(
                            "It may have been deleted permanently, or the id is wrong. wp-post "
                            "will not silently create a replacement. If you mean to start over, "
                            "remove the wordpress_id line and run sync to create a new draft."
                        ),
                    ) from None
                raise
            return remote, "wordpress_id"

        matches = ro.find_posts_by_slug(post.slug)
        if not matches:
            return None, "new"
        if len(matches) > 1:
            listing = "\n".join(
                f"  - id {m['id']} [{m['status']}] {raw(m, 'title')!r} {m.get('link', '')}"
                for m in sorted(matches, key=lambda m: m["id"])
            )
            raise RefusedError(
                f"{post.rel_path}: {len(matches)} WordPress posts have the slug {post.slug!r}; "
                f"refusing to guess which one this file is",
                details=listing,
                hint="Add `wordpress_id: <id>` to the front matter to choose one explicitly.",
            )
        return matches[0], "slug"

    def _check_linkage(
        self, post: Post, remote: dict[str, Any], state: SyncState | None, notes: list[str]
    ) -> None:
        """One WordPress post ↔ one Markdown file."""
        if not state or state.source == post.rel_path:
            return
        other = self.repo_root / state.source
        if other.exists():
            try:
                other_id = load_post(other, self.repo_root).wordpress_id
            except ValidationError:
                other_id = None
            if other_id in (None, remote["id"]):
                raise RefusedError(
                    f"WordPress post {remote['id']} is already linked to {state.source}, "
                    f"not {post.rel_path}",
                    hint=(
                        "If you moved or renamed the file, delete the old copy. If these are "
                        "different posts, give this file its own `slug:`."
                    ),
                )
        notes.append(f"file moved/renamed since last sync (was {state.source})")

    # rules ----------------------------------------------------------------------

    def _target_status(
        self, command: str, post: Post, remote: dict[str, Any] | None, resolved_by: str
    ) -> str:
        status = remote["status"] if remote else None
        slug_hint = ""
        if resolved_by == "slug":
            slug_hint = (
                f"\nNote: this file has no wordpress_id; it matched post {remote['id']} only "
                f"because both use the slug {post.slug!r}. If this file is a different post, "
                f"give it a distinct `slug:` in its front matter."
            )
        where = f"post {remote['id']} ({remote.get('link', '')})" if remote else ""

        if command == "sync":
            if status in LIVE or status == "future":
                raise RefusedError(
                    f"{where} is {status}; sync only manages drafts and never changes a "
                    f"live or scheduled post" + slug_hint,
                    hint=f"To change it in place, use: ./bin/wp-post update {post.rel_path}",
                )
            return status or "draft"

        if command == "publish":
            if not post.published_flag:
                raise RefusedError(f"{post.rel_path} has `published: false` in its front matter")
            if status in LIVE:
                raise RefusedError(
                    f"{where} is already {status}" + slug_hint,
                    hint=f"To change it in place, use: ./bin/wp-post update {post.rel_path}",
                )
            if status == "future":
                raise RefusedError(
                    f"{where} is already scheduled for {remote.get('date')}" + slug_hint,
                    hint="Use update to change its content or date; unschedule it in wp-admin.",
                )
            if post.date and to_utc(post.date, self.gmt_offset()) > self.now():
                return "future"
            return "publish"

        if command == "update":
            if remote is None:
                raise RefusedError(
                    f"no WordPress post found for {post.rel_path} (no wordpress_id, and no "
                    f"post has the slug {post.slug!r})",
                    hint="update never creates posts. Use sync for a draft, or publish.",
                )
            return status

        return status or "draft"  # status: informational only

    # plan --------------------------------------------------------------------------

    def plan(self, command: str, path: Path, opts: Options) -> Plan:
        ro = self.client.read_only_view()
        post = load_post(path, self.repo_root)
        warnings = list(post.warnings)
        notes: list[str] = []
        if has_block_delimiters(post.body):
            raise ValidationError(
                f"{post.rel_path}: body contains WordPress block comments (<!-- wp:... -->)",
                hint="They would corrupt the generated block structure; remove them.",
            )
        images, featured_img = collect_images(post, self.repo_root)

        remote, resolved_by = self._resolve(post, ro)
        if remote and remote.get("status") == "trash":
            raise RefusedError(
                f"post {remote['id']} is in the WordPress trash",
                hint="Restore it in wp-admin (Posts → Trash) first; wp-post will not recreate it.",
            )
        target = self._target_status(command, post, remote, resolved_by)
        state = SyncState.load(self.repo_root, remote["id"]) if remote else None
        if remote:
            self._check_linkage(post, remote, state, notes)
            if resolved_by == "slug":
                notes.append(f"matched existing post {remote['id']} by slug {post.slug!r}")

        # terms
        resolver = TermResolver(ro)
        tags = resolver.plan("tags", post.tags) if "tags" in post.front_matter else None
        cats = resolver.plan("categories", post.categories) if post.categories is not None else None
        warnings.extend(resolver.warnings)
        remote_cats = len(remote.get("categories") or []) if remote else 1
        term_count = combined_term_count(post.tags, post.categories, remote_cats)
        if term_count > READER_TERM_LIMIT:
            msg = (
                f"{term_count} tags+categories; WordPress.com Reader leaves posts with more than "
                f"{READER_TERM_LIMIT} out of its topic listings"
            )
            public = target in ("publish", "future") and command in ("publish", "update")
            if public and not opts.allow_many_terms:
                raise RefusedError(msg, hint="Trim the terms, or pass --allow-many-terms.")
            warnings.append(msg)

        # media
        media_planner = MediaPlanner(ro, MediaManifest(self.repo_root))
        all_imgs = images + ([featured_img] if featured_img else [])
        actions = media_planner.plan(all_imgs)
        by_src = {a.image.src: a for a in actions}
        media_actions = [by_src[i.src] for i in images]
        featured = by_src[featured_img.src] if featured_img else None

        content = render(post.body, {a.image.src: a.ref for a in media_actions}, post.slug)
        desired = self._desired(post, remote, state, content, tags, cats, featured, target)
        changed = self._changed(desired, remote, post)
        if remote and target != remote["status"]:
            changed.append("status")

        if remote and remote["status"] in LIVE and {"slug", "date"} & set(changed):
            what = " and ".join(sorted({"slug", "date"} & set(changed)))
            msg = (
                f"this would change the {what} of a live post, which changes its public URL "
                f"({remote.get('link')})"
            )
            if not opts.force and command != "status":
                raise RefusedError(
                    msg,
                    hint=(
                        "If that is intended, rerun with --force (WordPress redirects the old "
                        "URL). Otherwise make the front matter match the live post."
                    ),
                )
            warnings.append(msg)

        conflict = self._conflict(post, remote, state, desired, changed) if remote else None
        if (
            remote
            and state
            and not conflict
            and remote.get("modified_gmt") != state.remote_modified_gmt
        ):
            warnings.append(
                f"the post was saved in WordPress since the last sync "
                f"({remote.get('modified_gmt')} UTC), but its title, content, excerpt and "
                f"terms are unchanged; continuing"
            )

        # Unchanged since our last write, even if WordPress normalised what it stored.
        if (
            remote
            and state
            and not conflict
            and changed
            and state.sent_hash == payload_hash(desired)
            and state.remote_hashes == fingerprint(remote)
            and "status" not in changed
        ):
            changed = []

        first = command == "publish" and not (state and state.ever_published)
        return Plan(
            command=command,
            post=post,
            remote=remote,
            resolved_by=resolved_by,
            target_status=target,
            state=state,
            content=content,
            media=media_actions,
            featured=featured,
            tags=tags,
            categories=cats,
            desired=desired,
            changed=changed,
            conflict=conflict,
            term_count=term_count,
            first_publication=first,
            warnings=warnings,
            notes=notes,
        )

    def _desired(self, post, remote, state, content, tags, cats, featured, target) -> dict:
        d: dict[str, Any] = {"title": smarten(post.title), "content": content, "slug": post.slug}
        if post.excerpt is not None:
            d["excerpt"] = post.excerpt
        elif state and state.managed_excerpt:
            d["excerpt"] = ""  # excerpt removed from front matter: clear what we set
        if post.date is not None:
            d.update(wp_date_fields(post.date))
        if post.comment_status:
            d["comment_status"] = post.comment_status
        elif remote is None:
            d["comment_status"] = "open"
        if featured is not None:
            d["featured_media"] = featured.media_id or f"<upload {featured.image.rel}>"
        if tags is not None:
            d["tags"] = [t.term_id or f"<new {t.name}>" for t in tags]
        if cats is not None:
            d["categories"] = [c.term_id or f"<new {c.name}>" for c in cats]
        d["status"] = target
        return d

    def _changed(self, desired: dict, remote: dict | None, post: Post) -> list[str]:
        if remote is None:
            return sorted(k for k in desired if k != "status")
        out = []
        for key, value in desired.items():
            if key == "status":
                continue
            if key in ("date", "date_gmt"):
                if not date_matches(post.date, remote) and "date" not in out:
                    out.append("date")
            elif key in ("tags", "categories"):
                if sorted(map(str, value)) != sorted(map(str, remote.get(key) or [])):
                    out.append(key)
            elif key in ("title", "content", "excerpt"):
                if raw(remote, key).replace("\r\n", "\n").strip() != str(value).strip():
                    out.append(key)
            elif remote.get(key) != value:
                out.append(key)
        return out

    def _conflict(self, post, remote, state, desired, changed) -> Conflict | None:
        current = fingerprint(remote)
        managed = ["title", "content"]
        if "excerpt" in desired:
            managed.append("excerpt")
        managed += [k for k in ("tags", "categories") if k in desired]
        diff = self._diff(remote, desired)
        if state:
            moved = [k for k in managed if state.remote_hashes.get(k) != current[k]]
            if moved:
                return Conflict(
                    "changed",
                    moved,
                    remote.get("modified_gmt", ""),
                    state.remote_modified_gmt,
                    diff,
                )
            return None
        if post.wordpress_modified and post.wordpress_modified == remote.get("modified_gmt"):
            return None
        editorial = [k for k in ("title", "content", "excerpt") if k in changed]
        if editorial:
            return Conflict("no-baseline", editorial, remote.get("modified_gmt", ""), None, diff)
        return None

    @staticmethod
    def _diff(remote: dict, desired: dict, limit: int | None = 60) -> str:
        chunks = []
        for key in ("title", "excerpt", "content"):
            if key not in desired:
                continue
            old = raw(remote, key).replace("\r\n", "\n").strip().splitlines()
            new = str(desired[key]).strip().splitlines()
            chunks.extend(
                difflib.unified_diff(old, new, f"wordpress/{key}", f"local/{key}", n=1, lineterm="")
            )
        if limit and len(chunks) > limit:
            extra = len(chunks) - limit
            chunks = chunks[:limit] + [f"... ({extra} more diff lines; see `status --diff`)"]
        return "\n".join(chunks)

    def full_diff(self, plan: Plan) -> str:
        return self._diff(plan.remote or {}, plan.desired, limit=None)

    # execute -------------------------------------------------------------------------

    def execute(self, plan: Plan, opts: Options) -> dict[str, Any] | None:
        c = self.console
        for n in plan.notes:
            c.say(f"note: {n}")
        for w in plan.warnings:
            c.warn(w)

        if plan.conflict:
            text = plan.conflict.describe(self.config.edit_url(plan.post_id))
            if not opts.force:
                raise ConflictError(
                    f"conflict: {text}",
                    details=plan.conflict.diff or None,
                    hint=(
                        "Nothing was changed. Bring the Markdown up to date with the wp-admin "
                        "edits by hand, or rerun with --force to overwrite them with the "
                        "Markdown version. Old versions stay in WordPress revisions."
                    ),
                )
            c.warn(f"--force: overwriting remote changes. {text}")

        self._print_plan(plan)
        if plan.command == "publish":
            self._print_publication_summary(plan)

        if opts.dry_run:
            c.say("\nDry run: nothing was sent to WordPress and no files were changed.")
            return None

        if plan.action == "noop":
            self._record_local(plan, plan.remote, sent_hash=None)
            c.say("\nAlready up to date; nothing sent.")
            self._print_urls(plan.remote)
            return plan.remote

        if plan.command == "publish":
            self._confirm(plan, opts)

        result = self._apply(plan)
        verb = {"create": "Created", "update": "Updated"}[plan.action]
        c.say(f"\n{verb} post {result['id']} [{result['status']}]: {raw(result, 'title')}")
        self._print_urls(result)
        return result

    def _confirm(self, plan: Plan, opts: Options) -> None:
        if opts.yes:
            return
        if not self.isatty():
            raise RefusedError(
                "publishing needs confirmation and stdin is not a terminal",
                hint="Run it interactively, or pass --yes if you really mean it.",
            )
        answer = self.input_fn('\nType "publish" to make this post public: ')
        if answer.strip().lower() != "publish":
            raise AbortedError("not published (confirmation not given); nothing was changed")

    def _apply(self, plan: Plan) -> dict[str, Any]:
        rw = self.client
        resolver = TermResolver(rw)
        payload: dict[str, Any] = {}
        tag_ids = resolver.apply(plan.tags) if plan.tags is not None else None
        cat_ids = resolver.apply(plan.categories) if plan.categories is not None else None

        manifest = MediaManifest(self.repo_root)
        media_actions = plan.media + ([plan.featured] if plan.featured else [])
        MediaPlanner(rw, manifest).apply(media_actions)
        content = render(
            plan.post.body,
            {a.image.src: MediaRef(a.media_id, a.url or "") for a in plan.media},
            plan.post.slug,
        )

        final = dict(plan.desired)
        final["content"] = content
        if tag_ids is not None:
            final["tags"] = tag_ids
        if cat_ids is not None:
            final["categories"] = cat_ids
        if plan.featured is not None:
            final["featured_media"] = plan.featured.media_id

        if plan.action == "create":
            payload = final
            result = rw.create_post(payload)
        else:
            keys = set(plan.changed) - {"date", "status"}
            if "content" not in keys and content != plan.content:
                keys.add("content")
            payload = {k: final[k] for k in keys}
            if "date" in plan.changed:
                payload.update(wp_date_fields(plan.post.date))
            if "status" in plan.changed:
                payload["status"] = plan.target_status
            result = rw.update_post(plan.post_id, payload)

        self._record_local(plan, result, sent_hash=payload_hash(final))
        return result

    def _record_local(self, plan: Plan, remote: dict[str, Any], sent_hash: str | None) -> None:
        """Write the baseline state, then the wordpress_id into front matter."""
        prev = plan.state
        status = remote["status"]
        state = SyncState(
            wordpress_id=remote["id"],
            source=plan.post.rel_path,
            slug=remote.get("slug", ""),
            status=status,
            link=remote.get("link", ""),
            remote_modified_gmt=remote.get("modified_gmt", ""),
            remote_hashes=fingerprint(remote),
            sent_hash=sent_hash or (prev.sent_hash if prev else payload_hash(plan.desired)),
            ever_published=bool((prev and prev.ever_published) or status in LIVE | {"future"}),
            managed_excerpt=plan.post.excerpt is not None,
            synced_at=now_iso() if sent_hash or not prev else prev.synced_at,
        )
        if prev is None or _state_differs(prev, state):
            state.save(self.repo_root)
        if plan.post.wordpress_id != remote["id"]:
            try:
                if record_wordpress_id(plan.post.path, remote["id"]):
                    self.console.say(
                        f"Recorded wordpress_id: {remote['id']} in {plan.post.rel_path}"
                    )
            except (OSError, ValidationError) as exc:
                msg = getattr(exc, "message", str(exc))
                self.console.warn(
                    f"could not write wordpress_id to {plan.post.rel_path}: {msg}. "
                    f"Add `wordpress_id: {remote['id']}` to its front matter by hand."
                )

    # output ---------------------------------------------------------------------------

    def _print_plan(self, plan: Plan) -> None:
        c = self.console
        p = plan.post
        if plan.remote:
            r = plan.remote
            where = (
                f"post {r['id']} [{r['status']}] (found by {plan.resolved_by.replace('_', ' ')})"
            )
        else:
            where = "new post"
        c.say(f"{p.rel_path} → {where}")
        if plan.action == "create":
            c.say(f"  will create as: {plan.target_status}")
        elif plan.action == "noop":
            c.say("  no changes")
        else:
            c.say(f"  will update: {', '.join(plan.changed)}")
            if "status" in plan.changed:
                c.say(f"  status: {plan.remote['status']} → {plan.target_status}")
        for kind, plans in (("tag", plan.tags), ("category", plan.categories)):
            for t in plans or []:
                if t.create:
                    c.say(f"  will create {kind}: {t.name}")
                elif t.note:
                    c.say(f"  {kind} {t.name!r}: {t.note}")
        for a in plan.media + ([plan.featured] if plan.featured else []):
            if a.action == "upload":
                c.say(f"  will upload image: {a.image.rel} ({a.note})")
            elif a.action == "adopt":
                c.say(f"  reusing media {a.media_id} for {a.image.rel} ({a.note})")

    def _print_publication_summary(self, plan: Plan) -> None:
        p = plan.post
        c = self.console
        tags = ", ".join(t.name for t in plan.tags or []) or "(none)"
        if plan.categories is not None:
            cats = ", ".join(t.name for t in plan.categories) or "(none)"
        else:
            cats = "(not set locally: existing or default category)"
        current = plan.remote["status"] if plan.remote else "does not exist yet"
        c.say("")
        c.say("About to PUBLISH. This makes the post public.")
        c.say(f"  Title:       {p.title}")
        c.say(f"  Slug:        {p.slug}")
        c.say(f"  Date:        {describe_date(p)}")
        c.say(f"  Tags:        {tags}")
        c.say(f"  Categories:  {cats}")
        c.say(f"  Status:      {current} → {plan.target_status}")
        if plan.target_status == "future":
            c.say("  Scheduled:   WordPress will publish it at that date and time.")
        if p.date and plan.target_status == "publish":
            age = self.now() - to_utc(p.date, self.gmt_offset())
            if age > dt.timedelta(days=2):
                c.say(
                    f"  Note:        the date is {age.days} days ago; the post will be backdated."
                )
        if plan.first_publication:
            c.say(
                "  First publication: yes. When it goes live, WordPress may email it to "
                "subscribers (Jetpack Newsletter) and auto-share it to connected social accounts."
            )
        else:
            c.say("  First publication: no (this post was live before, per local sync state).")

    def _print_urls(self, remote: dict[str, Any]) -> None:
        c = self.console
        c.say(f"  Edit:    {self.config.edit_url(remote['id'])}")
        link = remote.get("link") or ""
        if remote["status"] == "publish":
            c.say(f"  Public:  {link}")
        elif link:
            sep = "&" if "?" in link else "?"
            c.say(f"  Preview: {link}{sep}preview=true")


def _state_differs(a: SyncState, b: SyncState) -> bool:
    keys = (
        "source",
        "slug",
        "status",
        "link",
        "remote_modified_gmt",
        "remote_hashes",
        "sent_hash",
        "ever_published",
        "managed_excerpt",
    )
    return any(getattr(a, k) != getattr(b, k) for k in keys)
