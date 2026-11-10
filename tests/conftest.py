"""Test fixtures: an in-memory fake of the WordPress REST API and a temp repo.

The fake implements just enough of wp/v2 (posts, tags, categories, media,
users/me, the index) to exercise wp-post, and records every request so tests
can assert on exactly what would have been sent. No test touches the network.
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import re
import struct
import textwrap
import zlib
from pathlib import Path
from urllib.parse import unquote

import pytest

from wp_post.cli import App, main
from wp_post.ui import Console

BASE = "https://blog.example"
USER = "matt"
PASSWORD = "abcd EFGH ijkl MNOP qrst UVWX"
NOW = dt.datetime(2026, 11, 10, 12, 0, tzinfo=dt.UTC)


def make_png(extra_chunk: tuple[bytes, bytes] | None = None, pixel: int = 0) -> bytes:
    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind
            + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 0, 0, 0, 0)
    out = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
    if extra_chunk:
        out += chunk(*extra_chunk)
    out += chunk(b"IDAT", zlib.compress(bytes([0, pixel]))) + chunk(b"IEND", b"")
    return out


class FakeResponse:
    def __init__(self, status: int, body=None, headers=None, content: bytes | None = None):
        self.status_code = status
        self.headers = {"Content-Type": "application/json", **(headers or {})}
        self.content = (
            content
            if content is not None
            else (json.dumps(body).encode() if body is not None else b"")
        )

    def json(self):
        return json.loads(self.content)


class FakeWordPress:
    def __init__(self):
        self.requests: list[dict] = []
        self.posts: dict[int, dict] = {}
        self.tags: dict[int, dict] = {}
        self.categories: dict[int, dict] = {
            1: {"id": 1, "name": "Uncategorized", "slug": "uncategorized"}
        }
        self.media: dict[int, dict] = {}
        self.files: dict[str, bytes] = {}
        self._next = 100
        self._clock = dt.datetime(2026, 11, 1, 9, 0, 0)
        self.auth = "Basic " + base64.b64encode(f"{USER}:{PASSWORD}".encode()).decode()
        self.capabilities = {
            c: True
            for c in (
                "edit_posts",
                "publish_posts",
                "edit_published_posts",
                "upload_files",
                "manage_categories",
                "unfiltered_html",
            )
        }

    # helpers for tests --------------------------------------------------------

    @property
    def writes(self) -> list[dict]:
        return [r for r in self.requests if r["method"] not in ("GET", "HEAD")]

    def next_id(self) -> int:
        self._next += 1
        return self._next

    def tick(self) -> str:
        self._clock += dt.timedelta(minutes=1)
        return self._clock.isoformat()

    def add_post(self, **fields) -> dict:
        pid = fields.pop("id", None) or self.next_id()
        post = {
            "id": pid,
            "status": "draft",
            "slug": "",
            "title": "",
            "content": "",
            "excerpt": "",
            "date": "2026-11-01T00:00:00",
            "date_gmt": "2026-11-01T00:00:00",
            "tags": [],
            "categories": [1],
            "comment_status": "open",
            "featured_media": 0,
        }
        post.update(fields)
        post["modified_gmt"] = self.tick()
        self.posts[pid] = post
        return post

    def admin_edit(self, pid: int, **fields) -> None:
        """Simulate someone editing the post in wp-admin."""
        self.posts[pid].update(fields)
        self.posts[pid]["modified_gmt"] = self.tick()

    def add_media(self, filename: str, data: bytes) -> dict:
        mid = self.next_id()
        url = f"{BASE}/wp-content/uploads/2026/11/{filename}"
        self.files[url] = data
        item = {"id": mid, "source_url": url, "media_details": {}}
        self.media[mid] = item
        return item

    def link(self, post: dict) -> str:
        if post["status"] == "publish":
            d = post["date"][:10].replace("-", "/")
            return f"{BASE}/{d}/{post['slug']}/"
        return f"{BASE}/?p={post['id']}"

    def view(self, post: dict) -> dict:
        out = dict(post)
        for key in ("title", "content", "excerpt"):
            out[key] = {"raw": post[key], "rendered": post[key]}
        out["link"] = self.link(post)
        return out

    # transport ------------------------------------------------------------------

    def request(
        self,
        method,
        url,
        params=None,
        json=None,
        data=None,
        headers=None,
        timeout=None,
        allow_redirects=True,
    ):
        params = dict(params or {})
        self.requests.append(
            {
                "method": method,
                "url": url,
                "params": params,
                "json": json,
                "headers": dict(headers or {}),
            }
        )
        if not url.startswith(f"{BASE}/wp-json"):
            if url in self.files:
                return FakeResponse(200, content=self.files[url])
            if url.startswith("https://public-api.wordpress.com/rest/v1.1/sites/"):
                return FakeResponse(200, {"ID": 1, "URL": BASE})
            return FakeResponse(404, content=b"not found")
        path = url[len(f"{BASE}/wp-json") :]
        if path == "/":
            return FakeResponse(
                200,
                {
                    "name": "Fake",
                    "url": BASE,
                    "gmt_offset": 0,
                    "namespaces": ["wp/v2"],
                    "authentication": {"application-passwords": {}},
                },
            )
        if (headers or {}).get("Authorization") != self.auth:
            return FakeResponse(
                401,
                {
                    "code": "incorrect_password",
                    "message": "The provided password is an invalid application password.",
                    "data": {"status": 401},
                },
            )
        return self.route(method, path, params, json, data, headers or {})

    def route(self, method, path, params, body, data, headers):
        m = re.fullmatch(r"/wp/v2/(posts|tags|categories|media)(?:/(\d+))?", path)
        if path == "/wp/v2/users/me":
            return FakeResponse(
                200,
                {
                    "id": 1,
                    "name": "Matt",
                    "roles": ["administrator"],
                    "capabilities": self.capabilities,
                },
            )
        if not m:
            return FakeResponse(404, {"code": "rest_no_route", "message": "No route"})
        kind, ident = m.group(1), m.group(2)
        ident = int(ident) if ident else None
        handler = getattr(self, f"_{kind}")
        return handler(method, ident, params, body, data, headers)

    def _paged(self, items, params):
        per = int(params.get("per_page", 10))
        page = int(params.get("page", 1))
        total_pages = max(1, -(-len(items) // per))
        chunk = items[(page - 1) * per : page * per]
        return FakeResponse(
            200, chunk, {"X-WP-TotalPages": str(total_pages), "X-WP-Total": str(len(items))}
        )

    def _posts(self, method, ident, params, body, data, headers):
        if method == "GET" and ident is None:
            statuses = set(params.get("status", "publish").split(","))
            items = [
                self.view(p)
                for p in sorted(self.posts.values(), key=lambda p: p["id"])
                if p["status"] in statuses and ("slug" not in params or p["slug"] == params["slug"])
            ]
            return self._paged(items, params)
        if ident is not None and ident not in self.posts:
            return FakeResponse(
                404,
                {
                    "code": "rest_post_invalid_id",
                    "message": "Invalid post ID.",
                    "data": {"status": 404},
                },
            )
        if method == "GET":
            return FakeResponse(200, self.view(self.posts[ident]))
        # create / update
        post = self.posts[ident] if ident else self.add_post(status="draft")
        fields = dict(body or {})
        if "date_gmt" in fields:
            fields["date"] = fields["date_gmt"]
        elif "date" in fields:
            fields["date_gmt"] = fields["date"]
        post.update(fields)
        if post["status"] in ("publish", "future"):
            future = dt.datetime.fromisoformat(post["date_gmt"]).replace(tzinfo=dt.UTC) > NOW
            post["status"] = "future" if future else "publish"
        post["modified_gmt"] = self.tick()
        return FakeResponse(201 if ident is None else 200, self.view(post))

    def _terms(self, store, method, ident, params, body):
        if method == "GET":
            q = (params.get("search") or "").lower()
            items = [t for t in store.values() if q in t["name"].lower() or q in t["slug"]]
            if "slug" in params:
                items = [t for t in store.values() if t["slug"] == params["slug"]]
            return self._paged(sorted(items, key=lambda t: t["id"]), params)
        name = body["name"]
        for t in store.values():
            if t["name"].lower() == name.lower():
                return FakeResponse(
                    400,
                    {
                        "code": "term_exists",
                        "message": "exists",
                        "data": {"status": 400, "term_id": t["id"]},
                    },
                )
        tid = self.next_id()
        store[tid] = {
            "id": tid,
            "name": name,
            "slug": re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-"),
        }
        return FakeResponse(201, store[tid])

    def _tags(self, method, ident, params, body, data, headers):
        return self._terms(self.tags, method, ident, params, body)

    def _categories(self, method, ident, params, body, data, headers):
        return self._terms(self.categories, method, ident, params, body)

    def _media(self, method, ident, params, body, data, headers):
        if method == "GET" and ident is None:
            return self._paged(sorted(self.media.values(), key=lambda x: x["id"]), params)
        if method == "GET":
            if ident not in self.media:
                return FakeResponse(404, {"code": "rest_post_invalid_id", "message": "Invalid"})
            return FakeResponse(200, self.media[ident])
        filename = unquote(
            re.search(r'filename="([^"]+)"', headers["Content-Disposition"]).group(1)
        )
        existing = {posixname(m["source_url"]) for m in self.media.values()}
        stem, dot, ext = filename.rpartition(".")
        n = 1
        while filename in existing:
            filename = f"{stem}-{n}.{ext}"
            n += 1
        return FakeResponse(201, self.add_media(filename, data))


def posixname(url: str) -> str:
    return url.rsplit("/", 1)[-1]


@pytest.fixture
def fake() -> FakeWordPress:
    return FakeWordPress()


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "_config.yml").write_text(f'url: "{BASE}"\n')
    for d in ("_posts", "_drafts", "assets/images"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "assets/images/photo.png").write_bytes(make_png())
    return tmp_path


def write_post(repo: Path, rel: str, front: str, body: str = "Hello world.\n") -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{textwrap.dedent(front).strip()}\n---\n\n{textwrap.dedent(body)}")
    return path


class Runner:
    def __init__(self, repo: Path, fake: FakeWordPress):
        self.repo = repo
        self.fake = fake
        self.answers: list[str] = []
        self.prompts: list[str] = []
        self.tty = True
        self.environ = {
            "WP_SITE_URL": BASE,
            "WP_USERNAME": USER,
            "WP_APPLICATION_PASSWORD": PASSWORD,
        }

    def _input(self, prompt: str) -> str:
        self.prompts.append(prompt)
        if not self.answers:
            raise AssertionError(f"unexpected prompt: {prompt}")
        return self.answers.pop(0)

    def __call__(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        app = App(
            repo_root=self.repo,
            environ=self.environ,
            session=self.fake,
            console=Console(out, err),
            input_fn=self._input,
            isatty=lambda: self.tty,
            keychain=None,
            now=lambda: NOW,
        )
        argv = [
            str(self.repo / a) if a.endswith(".md") and not a.startswith("/") else a for a in argv
        ]
        code = main(list(argv), app)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def run(repo: Path, fake: FakeWordPress) -> Runner:
    return Runner(repo, fake)
