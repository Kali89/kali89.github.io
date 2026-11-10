"""Local images → WordPress media library.

- Image paths resolve like Jekyll: `/assets/x.png` from the repository root,
  `x.png` relative to the Markdown file. External URLs are left alone.
- Each file is identified by its SHA-256. `.wordpress/media.json` (committed,
  no secrets) maps repo paths to {sha256, media id, url}.
- An image is only uploaded when no existing media item has identical bytes:
  first the manifest is checked, then the remote library, by filename plus a
  byte-for-byte comparison. That second step adopts images the migration
  already uploaded instead of duplicating them.
- A locally changed image (new hash) is uploaded as a new media item; the old
  one is kept. Remote media is never deleted.
- Images carrying GPS/EXIF data or hidden trailers (Motion Photos) are refused,
  using the same checks as the pre-commit hook (tools/image_metadata.py).
"""

from __future__ import annotations

import hashlib
import json
import mimetypes
import posixpath
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlparse

from wp_post.client import WordPressClient
from wp_post.document import Post, _atomic_write
from wp_post.errors import RemoteError, ValidationError
from wp_post.render import MediaRef, find_images

try:  # shared with the pre-commit hook; stdlib only
    from image_metadata import scan as scan_metadata
except ImportError:  # pragma: no cover - only if tools/ is not on sys.path
    scan_metadata = None

MANIFEST_PATH = ".wordpress/media.json"
PENDING_PREFIX = "wp-post-pending-upload:"


@dataclass(frozen=True)
class LocalImage:
    src: str  # exactly as written in the Markdown / front matter
    path: Path
    rel: str  # repository-relative, posix
    sha256: str
    mime: str


def is_external(src: str) -> bool:
    parsed = urlparse(src)
    return bool(parsed.scheme) or src.startswith("//")


def resolve_image_path(src: str, post_path: Path, repo_root: Path) -> Path:
    """Map an image src to a file in the repository (no existence check)."""
    clean = unquote(src.split("#", 1)[0].split("?", 1)[0])
    base = repo_root if clean.startswith("/") else post_path.parent
    resolved = (base / clean.lstrip("/")).resolve()
    try:
        resolved.relative_to(repo_root.resolve())
    except ValueError:
        raise ValidationError(f"image {src!r} points outside the repository") from None
    return resolved


def _load_local(src: str, post: Post, repo_root: Path) -> tuple[LocalImage | None, str | None]:
    try:
        path = resolve_image_path(src, post.path, repo_root)
    except ValidationError as exc:
        return None, exc.message
    rel = path.relative_to(repo_root.resolve()).as_posix()
    if not path.is_file():
        return None, f"{src!r} → {rel} does not exist"
    data = path.read_bytes()
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if not mime.startswith("image/"):
        return None, f"{src!r} → {rel} is not an image ({mime})"
    if scan_metadata is not None:
        issues = scan_metadata(data, str(path))
        if issues:
            return None, (
                f"{rel} has privacy-sensitive metadata ({'; '.join(issues)}). "
                f"Strip it: python3 tools/image_metadata.py strip {rel}"
            )
    return LocalImage(src, path, rel, hashlib.sha256(data).hexdigest(), mime), None


def collect_images(post: Post, repo_root: Path) -> tuple[list[LocalImage], LocalImage | None]:
    """Find and check every local image (body + featured_image). Raises a single
    ValidationError listing all problems, before anything is sent anywhere."""
    problems: list[str] = []
    images: dict[str, LocalImage] = {}
    for ref in find_images(post.body):
        if not ref.src:
            problems.append("an image has an empty src")
            continue
        if is_external(ref.src) or ref.src in images:
            continue
        img, problem = _load_local(ref.src, post, repo_root)
        if problem:
            problems.append(problem)
        elif img:
            images[ref.src] = img

    featured = None
    if post.featured_image:
        if is_external(post.featured_image):
            problems.append(
                "featured_image must be a local file in the repository (WordPress needs a "
                "media-library item, not a URL)"
            )
        else:
            featured, problem = _load_local(post.featured_image, post, repo_root)
            if problem:
                problems.append(f"featured_image: {problem}")

    if problems:
        raise ValidationError(
            f"{post.rel_path}: image problems:\n  - " + "\n  - ".join(problems),
            hint="Nothing was sent to WordPress.",
        )
    return list(images.values()), featured


class MediaManifest:
    def __init__(self, repo_root: Path):
        self.path = repo_root / MANIFEST_PATH
        self.data: dict[str, Any] = {"version": 1, "media": {}}
        if self.path.exists():
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if loaded.get("version") != 1:
                raise ValidationError(
                    f"{MANIFEST_PATH}: unsupported version {loaded.get('version')}"
                )
            self.data = loaded

    @property
    def entries(self) -> dict[str, dict[str, Any]]:
        return self.data["media"]

    def find(self, img: LocalImage) -> dict[str, Any] | None:
        entry = self.entries.get(img.rel)
        if entry and entry["sha256"] == img.sha256:
            return entry
        for other in self.entries.values():  # same bytes under another path
            if other["sha256"] == img.sha256:
                return other
        return None

    def record(self, img: LocalImage, media_id: int, url: str, how: str) -> None:
        old = self.entries.get(img.rel)
        entry: dict[str, Any] = {"sha256": img.sha256, "id": media_id, "url": url, "how": how}
        previous = list(old.get("previous", [])) if old else []
        if old and old["id"] != media_id:
            previous.append({"id": old["id"], "sha256": old["sha256"]})
        if previous:
            entry["previous"] = previous
        self.entries[img.rel] = entry

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.data["media"] = dict(sorted(self.entries.items()))
        text = json.dumps(self.data, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
        if self.path.exists() and self.path.read_text(encoding="utf-8") == text:
            return
        if not self.path.exists() and not self.entries:
            return
        _atomic_write(self.path, text.encode("utf-8"))


@dataclass
class MediaAction:
    image: LocalImage
    action: str  # "manifest" | "adopt" | "upload"
    media_id: int | None = None
    url: str | None = None
    note: str = ""

    @property
    def ref(self) -> MediaRef:
        if self.action == "upload" and self.media_id is None:
            return MediaRef(None, f"{PENDING_PREFIX}{self.image.rel}")
        return MediaRef(self.media_id, self.url or "")


@dataclass
class MediaPlanner:
    client: WordPressClient
    manifest: MediaManifest
    _library: list[dict[str, Any]] | None = field(default=None, init=False)

    def _remote_library(self) -> list[dict[str, Any]]:
        if self._library is None:
            self._library = self.client.get_all(
                "/wp/v2/media",
                {
                    "media_type": "image",
                    "_fields": "id,source_url,media_details",
                    "orderby": "id",
                    "order": "asc",
                },
            )
        return self._library

    def _exists(self, media_id: int) -> bool:
        try:
            self.client.get(f"/wp/v2/media/{media_id}", {"_fields": "id"})
            return True
        except RemoteError as exc:
            if getattr(exc, "wp_code", "") in ("rest_post_invalid_id", "rest_forbidden"):
                return False
            raise

    def _adoptable(self, img: LocalImage) -> dict[str, Any] | None:
        name = img.path.name
        stem, ext = posixpath.splitext(name)
        variant = re.compile(rf"^{re.escape(stem)}(-\d+|-scaled)?{re.escape(ext)}$", re.IGNORECASE)
        for item in self._remote_library():
            url = item.get("source_url") or ""
            base = posixpath.basename(urlparse(url).path)
            original = (item.get("media_details") or {}).get("original_image")
            if not (variant.match(base) or original == name):
                continue
            candidate_url = posixpath.join(posixpath.dirname(url), original) if original else url
            try:
                data = self.client.download(candidate_url)
            except RemoteError:
                continue
            if hashlib.sha256(data).hexdigest() == img.sha256:
                return item
        return None

    def plan(self, images: list[LocalImage]) -> list[MediaAction]:
        actions = []
        for img in images:
            entry = self.manifest.find(img)
            if entry and self._exists(entry["id"]):
                actions.append(MediaAction(img, "manifest", entry["id"], entry["url"]))
                continue
            note = "recorded media item no longer exists; " if entry else ""
            item = self._adoptable(img)
            if item:
                actions.append(
                    MediaAction(
                        img,
                        "adopt",
                        item["id"],
                        item["source_url"],
                        note + "identical file already in media library",
                    )
                )
            else:
                changed = img.rel in self.manifest.entries and not entry
                why = "changed locally" if changed else "not in media library"
                actions.append(MediaAction(img, "upload", note=note + why))
        return actions

    def apply(self, actions: list[MediaAction]) -> None:
        """Upload what needs uploading and record everything in the manifest.
        The manifest is saved after each upload, so a crash cannot cause a
        re-upload of the same bytes."""
        for act in actions:
            if act.action == "upload" and act.media_id is None:
                filename = act.image.path.name.replace('"', "")
                resp = self.client.request(
                    "POST",
                    "/wp/v2/media",
                    data=act.image.path.read_bytes(),
                    headers={
                        "Content-Type": act.image.mime,
                        "Content-Disposition": f'attachment; filename="{filename}"',
                    },
                ).body
                act.media_id, act.url = int(resp["id"]), resp["source_url"]
                self.manifest.record(act.image, act.media_id, act.url, "uploaded")
                self.manifest.save()
            elif act.action == "adopt":
                self.manifest.record(act.image, act.media_id, act.url, "adopted")
            elif act.action == "manifest" and act.image.rel not in self.manifest.entries:
                self.manifest.record(act.image, act.media_id, act.url, "reused")
        self.manifest.save()
