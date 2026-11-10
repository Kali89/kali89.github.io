"""Command-line interface: ./bin/wp-post <command> ...

Run `./bin/wp-post --help` or see docs/wordpress-publishing.md.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys
import traceback
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wp_post import __version__
from wp_post.client import WordPressClient
from wp_post.config import KeychainLookup, keychain_lookup, load_config, require_credentials
from wp_post.doctor import Doctor, setup
from wp_post.document import iter_post_files, load_post
from wp_post.errors import EXIT_CODES, ValidationError, WPPostError
from wp_post.publisher import Options, Plan, Publisher, describe_date
from wp_post.redaction import redact
from wp_post.state import raw
from wp_post.ui import Console
from wp_post.validate import validate_files

REPO_ROOT = Path(__file__).resolve().parents[2]

EPILOG = "exit statuses:\n" + "\n".join(f"  {k}  {v}" for k, v in EXIT_CODES.items())


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="wp-post",
        description=(
            "Sync this repository's Markdown posts to WordPress. Git is canonical; "
            "nothing goes live without an explicit `publish`."
        ),
        epilog=EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version=f"wp-post {__version__}")
    sub = p.add_subparsers(dest="command", metavar="COMMAND")

    d = sub.add_parser("doctor", help="check config, auth and permissions (read-only)")
    d.add_argument("--setup", action="store_true", help="interactively store credentials first")

    s = sub.add_parser("status", help="show how a file relates to WordPress (read-only)")
    s.add_argument("file", type=Path)
    s.add_argument("--diff", action="store_true", help="show the full content diff")

    def writer(name: str, help_: str, *, yes: bool = False, terms: bool = False):
        w = sub.add_parser(name, help=help_)
        w.add_argument("file", type=Path)
        w.add_argument(
            "--dry-run",
            "-n",
            action="store_true",
            help="show what would happen; send no writes, change no files",
        )
        w.add_argument(
            "--force",
            action="store_true",
            help="overwrite remote edits / allow a live URL change after a safety stop",
        )
        if yes:
            w.add_argument(
                "--yes", action="store_true", help="skip the confirmation prompt (never implied)"
            )
        if terms:
            w.add_argument(
                "--allow-many-terms",
                action="store_true",
                help="publish even with more than 15 tags+categories",
            )
        return w

    writer("sync", "create or update a WordPress DRAFT (never touches live posts)")
    writer("publish", "make a post public for the first time (asks first)", yes=True, terms=True)
    writer("update", "update an existing post in place, keeping its status", terms=True)

    v = sub.add_parser("validate", help="check files offline (no network, no credentials)")
    v.add_argument("files", type=Path, nargs="*")
    v.add_argument("--all", action="store_true", help="check every file in _posts/ and _drafts/")

    sub.add_parser("list", help="list WordPress posts and their local files (read-only)")
    return p


class App:
    def __init__(
        self,
        repo_root: Path = REPO_ROOT,
        environ: Mapping[str, str] | None = None,
        session: Any = None,
        console: Console | None = None,
        input_fn: Callable[[str], str] = input,
        isatty: Callable[[], bool] | None = None,
        keychain: KeychainLookup | None = keychain_lookup,
        now: Callable[[], dt.datetime] | None = None,
        getpass_fn: Callable[[str], str] | None = None,
    ):
        self.repo_root = repo_root.resolve()
        self.environ = environ
        self.session = session
        self.console = console or Console()
        self.input_fn = input_fn
        self.isatty = isatty or (lambda: sys.stdin.isatty())
        self.keychain = keychain
        self.now = now
        self.getpass_fn = getpass_fn

    def path(self, p: Path) -> Path:
        return p if p.is_absolute() else (Path.cwd() / p)

    def publisher(self) -> Publisher:
        cfg = load_config(self.repo_root, self.environ, self.keychain)
        require_credentials(cfg)
        client = WordPressClient(cfg.site_url, cfg.username, cfg.password, session=self.session)
        kw: dict[str, Any] = {"input_fn": self.input_fn, "isatty": self.isatty}
        if self.now:
            kw["now"] = self.now
        return Publisher(self.repo_root, cfg, client, self.console, **kw)

    # commands -------------------------------------------------------------------

    def cmd_doctor(self, args) -> int:
        if args.setup:
            kw = {"input_fn": self.input_fn, "isatty": self.isatty}
            if self.getpass_fn:
                kw["getpass_fn"] = self.getpass_fn
            setup(self.repo_root, self.console, **kw)
        return Doctor(self.repo_root, self.console, self.session, self.environ, self.keychain).run()

    def cmd_write(self, args) -> int:
        opts = Options(
            dry_run=args.dry_run,
            force=args.force,
            yes=getattr(args, "yes", False),
            allow_many_terms=getattr(args, "allow_many_terms", False),
        )
        pub = self.publisher()
        plan = pub.plan(args.command, self.path(args.file), opts)
        pub.execute(plan, opts)
        return 0

    def cmd_status(self, args) -> int:
        pub = self.publisher()
        plan = pub.plan("status", self.path(args.file), Options(dry_run=True))
        self._print_status(pub, plan, args.diff)
        return 0

    def _print_status(self, pub: Publisher, plan: Plan, full_diff: bool) -> None:
        c, p, r = self.console, plan.post, plan.remote
        c.say(f"File:       {p.rel_path} ({p.kind})")
        c.say(f"Title:      {p.title}")
        c.say(f"Slug:       {p.slug} (from {p.slug_source})")
        c.say(f"Date:       {describe_date(p)}")
        c.say(f"Tags:       {', '.join(p.tags) or '(none)'}")
        if p.categories is not None:
            c.say(f"Categories: {', '.join(p.categories) or '(none)'}")
        for n in plan.notes:
            c.say(f"note: {n}")
        for w in plan.warnings:
            c.warn(w)
        if r is None:
            c.say("\nWordPress:  no matching post")
            c.say(f"Next:       ./bin/wp-post sync {p.rel_path}   (creates a draft)")
            return
        c.say(
            f"\nWordPress:  post {r['id']} [{r['status']}], found by "
            f"{plan.resolved_by.replace('_', ' ')}"
        )
        c.say(f"Modified:   {r.get('modified_gmt')} UTC")
        c.say(f"Edit:       {pub.config.edit_url(r['id'])}")
        c.say(f"Link:       {r.get('link')}")
        if plan.state:
            c.say(
                f"Last sync:  {plan.state.synced_at} (remote then: "
                f"{plan.state.remote_modified_gmt} UTC)"
            )
        else:
            c.say("Last sync:  never from this repository (no baseline recorded)")
        if plan.changed:
            c.say(f"Local vs WordPress: differs in {', '.join(plan.changed)}")
        else:
            c.say("Local vs WordPress: in sync")
        if plan.conflict:
            c.say("Conflict:   " + plan.conflict.describe(pub.config.edit_url(r["id"])))
            c.say("            sync/update will stop; --force overwrites the remote version")
        else:
            c.say("Conflict:   none")
        status = r["status"]
        nxt = {
            "draft": f"sync (update draft) or publish {p.rel_path}",
            "pending": f"sync (update) or publish {p.rel_path}",
            "future": f"update {p.rel_path} (scheduled; keeps its schedule)",
            "publish": f"update {p.rel_path} (live; changes it in place)",
            "private": f"update {p.rel_path} (private; stays private)",
        }.get(status)
        if nxt:
            c.say(f"Next:       ./bin/wp-post {nxt}")
        if plan.changed and (full_diff or plan.conflict):
            diff = (
                pub.full_diff(plan) if full_diff else (plan.conflict.diff if plan.conflict else "")
            )
            if diff:
                c.say("\n" + diff)

    def cmd_validate(self, args) -> int:
        files = [self.path(f) for f in args.files]
        if args.all:
            files += iter_post_files(self.repo_root)
        if not files:
            raise ValidationError("nothing to validate", hint="Pass files, or --all.")
        report = validate_files(files, self.repo_root)
        for w in report.warnings:
            self.console.warn(w)
        for e in report.errors:
            self.console.error(e)
        self.console.say(
            f"Checked {report.checked} file(s): {len(report.errors)} error(s), "
            f"{len(report.warnings)} warning(s)."
        )
        return ValidationError.exit_code if report.errors else 0

    def cmd_list(self, args) -> int:
        pub = self.publisher()
        ro = pub.client.read_only_view()
        remote = ro.get_all(
            "/wp/v2/posts",
            {
                "status": "publish,future,draft,pending,private",
                "context": "edit",
                "_fields": "id,slug,status,date,title,link",
            },
        )
        by_id, by_slug = {}, {}
        for f in iter_post_files(self.repo_root):
            try:
                post = load_post(f, self.repo_root)
            except ValidationError:
                continue
            if post.wordpress_id:
                by_id[post.wordpress_id] = post.rel_path
            by_slug.setdefault(post.slug, post.rel_path)
        seen = set()
        c = self.console
        c.say(f"{'STATUS':<8} {'ID':>6}  {'DATE':<10}  {'LOCAL FILE':<55} TITLE")
        for r in sorted(remote, key=lambda r: r.get("date") or "", reverse=True):
            local = by_id.get(r["id"]) or (
                f"{by_slug[r['slug']]} (by slug)" if r.get("slug") in by_slug else "(no local file)"
            )
            seen.add(local.split(" ")[0])
            c.say(
                f"{r['status']:<8} {r['id']:>6}  {(r.get('date') or '')[:10]:<10}  "
                f"{local:<55} {raw(r, 'title')}"
            )
        unlinked = sorted(set(by_id.values()) | set(by_slug.values()))
        missing = [f for f in unlinked if f not in seen]
        if missing:
            c.say("\nLocal files with no WordPress post:")
            for f in missing:
                c.say(f"  {f}")
        return 0


def main(argv: list[str] | None = None, app: App | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    app = app or App()
    handler = {
        "doctor": app.cmd_doctor,
        "status": app.cmd_status,
        "sync": app.cmd_write,
        "publish": app.cmd_write,
        "update": app.cmd_write,
        "validate": app.cmd_validate,
        "list": app.cmd_list,
    }[args.command]
    c = app.console
    try:
        return handler(args)
    except WPPostError as exc:
        c.error(exc.message)
        if exc.details:
            for line in str(exc.details).splitlines():
                c.detail(f"    {line}")
        if exc.hint:
            c.detail(f"hint: {exc.hint}")
        return exc.exit_code
    except KeyboardInterrupt:
        c.error("interrupted")
        return 130
    except Exception as exc:  # noqa: BLE001 - last-resort, redacted report
        c.error(f"unexpected {type(exc).__name__}: {exc}")
        c.detail(redact("".join(traceback.format_exception(exc)[-6:])))
        return 1
