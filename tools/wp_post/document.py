"""Read Jekyll-style Markdown posts: front matter, filename date/slug, identity.

The only change wp-post ever makes to a Markdown file is to insert one line,
`wordpress_id: N`, before the closing `---` of the front matter, after the
post first exists in WordPress. Everything else in the file is left byte-for-byte
intact, so the rest of the front matter keeps its formatting.
"""

from __future__ import annotations

import datetime as dt
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from wp_post.errors import ValidationError

FILENAME_DATE_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})-(.+)$")
MD_SUFFIXES = {".md", ".markdown"}
# Jekyll-only keys we accept but never send to WordPress.
IGNORED_KEYS = {"layout", "author", "permalink", "redirect_from", "sitemap"}
COMMENT_STATUSES = {"open", "closed"}

DateValue = dt.date | dt.datetime


@dataclass
class Post:
    path: Path
    rel_path: str
    body: str
    front_matter: dict[str, Any]
    title: str
    slug: str
    slug_source: str
    date: DateValue | None
    date_source: str | None
    tags: list[str]
    categories: list[str] | None  # None = not specified locally (leave remote alone)
    excerpt: str | None
    featured_image: str | None
    wordpress_id: int | None
    comment_status: str | None  # None = not specified locally
    published_flag: bool  # Jekyll's `published: false` blocks publishing
    wordpress_modified: str | None  # optional baseline hint in front matter
    warnings: list[str] = field(default_factory=list)

    @property
    def kind(self) -> str:
        top = self.rel_path.split("/", 1)[0]
        return {"_drafts": "draft", "_posts": "post"}.get(top, "other")


def slugify(text: str) -> str:
    """Jekyll's default slugify: lowercase, runs of non-alphanumerics become '-'."""
    return re.sub(r"[\W_]+", "-", text.lower(), flags=re.UNICODE).strip("-")


def split_front_matter(text: str, path: Path) -> tuple[str, str, int]:
    """Return (front_matter_yaml, body, closing_delimiter_line_index)."""
    if text.startswith("﻿"):
        text = text[1:]
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n").rstrip() != "---":
        raise ValidationError(
            f"{path}: no front matter",
            hint="Posts must start with a '---' line, front matter, and a closing '---'.",
        )
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n").rstrip() in ("---", "..."):
            return "".join(lines[1:i]), "".join(lines[i + 1 :]), i
    raise ValidationError(f"{path}: front matter is not closed with '---'")


def _as_term_list(value: Any, key: str, path: Path) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        # Jekyll splits a string value on whitespace.
        return value.split()
    if isinstance(value, list):
        out = []
        for item in value:
            if not isinstance(item, (str, int, float)) or isinstance(item, bool):
                raise ValidationError(f"{path}: every entry in `{key}` must be text")
            name = str(item).strip()
            if name:
                out.append(name)
        return out
    raise ValidationError(f"{path}: `{key}` must be a list, e.g. {key}: [one, two]")


def _parse_date(value: Any, path: Path) -> DateValue:
    if isinstance(value, (dt.datetime, dt.date)):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
                return dt.date.fromisoformat(text)
            # Jekyll style: "2026-11-12 09:30:00 +0000"
            m = re.fullmatch(
                r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)\s*([+-]\d{2}:?\d{2}|Z)?", text
            )
            if m:
                tz = m.group(3) or ""
                if tz and tz != "Z" and ":" not in tz:
                    tz = f"{tz[:3]}:{tz[3:]}"
                return dt.datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}{tz}")
        except ValueError:
            pass
    raise ValidationError(
        f"{path}: unrecognised date {value!r}",
        hint="Use YYYY-MM-DD, or 'YYYY-MM-DD HH:MM:SS +0000' for a specific time.",
    )


def _dedupe_casefold(names: list[str], key: str, warnings: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for name in names:
        folded = name.casefold()
        if folded in seen:
            if seen[folded] != name:
                warnings.append(
                    f"`{key}` lists {seen[folded]!r} and {name!r}; using {seen[folded]!r}"
                )
            continue
        seen[folded] = name
    return list(seen.values())


def load_post(path: Path, repo_root: Path) -> Post:
    path = path.resolve()
    repo_root = repo_root.resolve()
    try:
        rel = path.relative_to(repo_root).as_posix()
    except ValueError:
        raise ValidationError(f"{path} is not inside the repository {repo_root}") from None
    if path.suffix.lower() not in MD_SUFFIXES:
        raise ValidationError(f"{rel}: expected a .md or .markdown file")
    if not path.is_file():
        raise ValidationError(f"{rel}: file not found")

    text = path.read_text(encoding="utf-8")
    fm_text, body, _ = split_front_matter(text, Path(rel))
    try:
        fm = yaml.safe_load(fm_text) or {}
    except yaml.YAMLError as exc:
        raise ValidationError(f"{rel}: front matter is not valid YAML: {exc}") from None
    if not isinstance(fm, dict):
        raise ValidationError(f"{rel}: front matter must be a mapping of key: value pairs")

    warnings: list[str] = []
    p = Path(rel)

    title = fm.get("title")
    if not isinstance(title, str) or not title.strip():
        raise ValidationError(
            f"{rel}: `title` is missing or not text",
            hint='Quote titles that YAML could misread, e.g. title: "No".',
        )

    stem = path.stem
    m = FILENAME_DATE_RE.match(stem)
    filename_date = None
    filename_slug = stem
    if m:
        try:
            filename_date = dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise ValidationError(f"{rel}: filename date is not a real date") from None
        filename_slug = m.group(4)

    if fm.get("slug") is not None:
        slug = slugify(str(fm["slug"]))
        slug_source = "front matter"
    else:
        slug = slugify(filename_slug)
        slug_source = "filename"
    if not slug:
        raise ValidationError(f"{rel}: could not derive a slug; add `slug:` to the front matter")

    date: DateValue | None = None
    date_source = None
    if fm.get("date") is not None:
        date, date_source = _parse_date(fm["date"], p), "front matter"
    elif filename_date:
        date, date_source = filename_date, "filename"
    if filename_date and date_source == "front matter":
        fm_day = date.date() if isinstance(date, dt.datetime) else date
        if fm_day != filename_date:
            warnings.append(
                f"front matter date {fm_day} differs from the filename date {filename_date}; "
                f"the front matter date wins (as in Jekyll)"
            )

    tags = _dedupe_casefold(_as_term_list(fm.get("tags"), "tags", p), "tags", warnings)
    categories = None
    for key in ("categories", "category"):
        if key in fm:
            categories = _dedupe_casefold(_as_term_list(fm.get(key), key, p), key, warnings)
            break

    excerpt = fm.get("excerpt")
    if excerpt is not None and not isinstance(excerpt, str):
        raise ValidationError(f"{rel}: `excerpt` must be text")

    featured = fm.get("featured_image")
    if featured is not None and (not isinstance(featured, str) or not featured.strip()):
        raise ValidationError(f"{rel}: `featured_image` must be a path to an image")

    wp_id = fm.get("wordpress_id")
    if wp_id is not None and (isinstance(wp_id, bool) or not isinstance(wp_id, int) or wp_id <= 0):
        raise ValidationError(f"{rel}: `wordpress_id` must be a positive integer")

    comment_status = None
    if "comment_status" in fm:
        comment_status = str(fm["comment_status"]).strip().lower()
        if comment_status not in COMMENT_STATUSES:
            raise ValidationError(f"{rel}: `comment_status` must be open or closed")
    elif "comments" in fm:
        if not isinstance(fm["comments"], bool):
            raise ValidationError(f"{rel}: `comments` must be true or false")
        comment_status = "open" if fm["comments"] else "closed"

    published_flag = fm.get("published", True) is not False

    if "permalink" in fm:
        warnings.append("`permalink` is ignored; WordPress uses the site's permalink structure")
    if re.search(r"\{%|\{\{", body):
        warnings.append("body contains Liquid tags ({% %} / {{ }}); they are sent literally")

    modified = fm.get("wordpress_modified")
    return Post(
        path=path,
        rel_path=rel,
        body=body,
        front_matter=fm,
        title=title.strip(),
        slug=slug,
        slug_source=slug_source,
        date=date,
        date_source=date_source,
        tags=tags,
        categories=categories,
        excerpt=excerpt,
        featured_image=featured.strip() if isinstance(featured, str) else None,
        wordpress_id=wp_id,
        comment_status=comment_status,
        published_flag=published_flag,
        wordpress_modified=str(modified) if modified is not None else None,
        warnings=warnings,
    )


def iter_post_files(repo_root: Path) -> list[Path]:
    files = []
    for folder in ("_posts", "_drafts"):
        d = repo_root / folder
        if d.is_dir():
            files.extend(p for p in d.rglob("*") if p.suffix.lower() in MD_SUFFIXES)
    return sorted(files)


def record_wordpress_id(path: Path, post_id: int) -> bool:
    """Insert `wordpress_id: N` into the front matter. Returns True if the file
    changed. Refuses to replace a different existing id."""
    raw = path.read_bytes()
    text = raw.decode("utf-8")
    newline = "\r\n" if "\r\n" in text else "\n"
    bom = "﻿" if text.startswith("﻿") else ""
    _, _, close_idx = split_front_matter(text, path)
    lines = text[len(bom) :].splitlines(keepends=True)

    for line in lines[1:close_idx]:
        m = re.match(r"^wordpress_id\s*:\s*(.*?)\s*$", line.rstrip("\r\n"))
        if m:
            if m.group(1) == str(post_id):
                return False
            raise ValidationError(
                f"{path.name}: front matter already has wordpress_id: {m.group(1)}, "
                f"refusing to change it to {post_id}"
            )

    lines.insert(close_idx, f"wordpress_id: {post_id}{newline}")
    new_text = bom + "".join(lines)
    _atomic_write(path, new_text.encode("utf-8"))
    return True


def _atomic_write(path: Path, data: bytes) -> None:
    mode = path.stat().st_mode if path.exists() else 0o644
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode & 0o7777)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
