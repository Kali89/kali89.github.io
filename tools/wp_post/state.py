"""Per-post sync state: the baseline used for conflict detection.

Stored in `.wordpress/posts/<wordpress_id>.json` (committed; no secrets).

Why not keep all of this in front matter? The post ID is identity and belongs
with the file: it survives renames and moves from _drafts/ to _posts/, so it
lives in front matter. The baseline below changes on every sync. Writing it into
front matter would rewrite the file you have open in Vim each time and add noise
to every post's diff, so it lives here instead, keyed by that stable ID.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from wp_post.document import _atomic_write

STATE_DIR = ".wordpress/posts"
VERSION = 1

# Remote fields whose change we treat as an editorial edit (conflict-worthy).
TRACKED = ("title", "content", "excerpt", "tags", "categories")


def _norm(text: str | None) -> str:
    return (text or "").replace("\r\n", "\n").strip()


def digest(value: Any) -> str:
    if isinstance(value, list):
        value = ",".join(str(v) for v in sorted(value))
    return hashlib.sha256(_norm(str(value)).encode("utf-8")).hexdigest()[:16]


def raw(post: dict[str, Any], key: str) -> str:
    value = post.get(key)
    if isinstance(value, dict):
        return value.get("raw", value.get("rendered", "")) or ""
    return value or ""


def fingerprint(remote: dict[str, Any]) -> dict[str, str]:
    return {
        "title": digest(raw(remote, "title")),
        "content": digest(raw(remote, "content")),
        "excerpt": digest(raw(remote, "excerpt")),
        "tags": digest(remote.get("tags") or []),
        "categories": digest(remote.get("categories") or []),
    }


@dataclass
class SyncState:
    wordpress_id: int
    source: str
    slug: str
    status: str
    link: str
    remote_modified_gmt: str
    remote_hashes: dict[str, str]
    sent_hash: str
    ever_published: bool = False
    managed_excerpt: bool = False
    synced_at: str = ""
    version: int = VERSION
    extra: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def path_for(repo_root: Path, post_id: int) -> Path:
        return repo_root / STATE_DIR / f"{post_id}.json"

    @classmethod
    def load(cls, repo_root: Path, post_id: int) -> SyncState | None:
        path = cls.path_for(repo_root, post_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})

    def save(self, repo_root: Path) -> Path:
        path = self.path_for(repo_root, self.wordpress_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(asdict(self), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        _atomic_write(path, text.encode("utf-8"))
        return path


def payload_hash(payload: dict[str, Any]) -> str:
    """Hash of what we asked WordPress to store, so an unchanged file is a no-op
    even if WordPress normalises the content it saves."""
    text = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
