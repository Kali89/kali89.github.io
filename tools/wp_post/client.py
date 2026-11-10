"""Thin client for the WordPress REST API (wp/v2) with Application Password auth.

Safety properties:
- Redirects are never followed for API calls. A redirected POST silently turns
  into a GET in most HTTP stacks, which would look like success.
- A client built with read_only=True raises before sending any write. Dry runs
  and read-only commands use one, so a bug cannot turn them into writes.
- The Authorization header is built here and never logged.
"""

from __future__ import annotations

import json as jsonlib
from dataclasses import dataclass
from typing import Any

import requests

from wp_post import __version__
from wp_post.errors import ConfigError, RemoteError, WPPostError
from wp_post.redaction import redact, register_basic_auth

USER_AGENT = f"wp-post/{__version__} (+markdown publisher)"
READ_METHODS = {"GET", "HEAD", "OPTIONS"}


class ReadOnlyViolation(WPPostError):
    exit_code = 1


@dataclass
class Response:
    status: int
    headers: dict[str, str]
    body: Any
    content: bytes = b""

    def header(self, name: str) -> str | None:
        for key, value in self.headers.items():
            if key.lower() == name.lower():
                return value
        return None


class WordPressClient:
    def __init__(
        self,
        site_url: str,
        username: str | None = None,
        password: str | None = None,
        *,
        session: Any = None,
        read_only: bool = False,
        timeout: float = 30.0,
    ):
        self.site_url = site_url.rstrip("/")
        self.api_root = f"{self.site_url}/wp-json"
        self.session = session or requests.Session()
        self.read_only = read_only
        self.timeout = timeout
        self._auth_header = (
            register_basic_auth(username, password) if username and password else None
        )
        self.writes = 0  # number of write requests sent (for tests/diagnostics)

    @property
    def authenticated(self) -> bool:
        return self._auth_header is not None

    def read_only_view(self) -> WordPressClient:
        clone = object.__new__(WordPressClient)
        clone.__dict__.update(self.__dict__)
        clone.read_only = True
        return clone

    # -- low level -----------------------------------------------------------

    def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any = None,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Response:
        method = method.upper()
        if self.read_only and method not in READ_METHODS:
            raise ReadOnlyViolation(
                f"internal safety stop: refusing {method} {path} in read-only mode",
                hint="This is a bug in wp-post; nothing was sent.",
            )
        url = path if path.startswith("https://") else f"{self.api_root}{path}"
        send_headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        if headers:
            send_headers.update(headers)
        if auth:
            if not self._auth_header:
                raise ConfigError(
                    "this command needs WordPress credentials",
                    hint="Run ./bin/wp-post doctor to check your configuration.",
                )
            send_headers["Authorization"] = self._auth_header
        if method not in READ_METHODS:
            self.writes += 1
        try:
            resp = self.session.request(
                method,
                url,
                params=params,
                json=json,
                data=data,
                headers=send_headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise RemoteError(
                f"network error talking to {self.site_url}: {type(exc).__name__}",
                hint="Check your connection and that WP_SITE_URL is correct.",
                details=redact(exc),
            ) from None

        try:
            body = resp.json() if resp.content else None
        except ValueError:
            body = None
        result = Response(resp.status_code, dict(resp.headers), body, resp.content)
        if 300 <= resp.status_code < 400:
            raise RemoteError(
                f"{method} {path} was redirected (HTTP {resp.status_code}) to "
                f"{result.header('Location')}",
                hint="Set WP_SITE_URL to the site's canonical https:// address.",
            )
        if resp.status_code >= 400:
            raise _api_error(method, path, result)
        return result

    def get(self, path: str, params: dict[str, Any] | None = None, **kw: Any) -> Any:
        return self.request("GET", path, params=params, **kw).body

    def post(self, path: str, json: Any = None, params: dict[str, Any] | None = None) -> Any:
        return self.request("POST", path, json=json, params=params).body

    def get_all(self, path: str, params: dict[str, Any] | None = None) -> list[Any]:
        """GET every page of a collection endpoint."""
        params = dict(params or {})
        params.setdefault("per_page", 100)
        page, items = 1, []
        while True:
            params["page"] = page
            resp = self.request("GET", path, params=params)
            items.extend(resp.body or [])
            total_pages = int(resp.header("X-WP-TotalPages") or 1)
            if page >= total_pages:
                return items
            page += 1

    def download(self, url: str) -> bytes:
        """Fetch a public file (e.g. an uploaded image) without credentials."""
        try:
            resp = self.session.request(
                "GET",
                url,
                headers={"User-Agent": USER_AGENT},
                timeout=self.timeout,
                allow_redirects=True,
            )
        except requests.RequestException as exc:
            raise RemoteError(f"could not download {url}: {type(exc).__name__}") from None
        if resp.status_code != 200:
            raise RemoteError(f"could not download {url}: HTTP {resp.status_code}")
        return resp.content

    # -- wp/v2 helpers -------------------------------------------------------

    def get_post(self, post_id: int) -> dict[str, Any]:
        return self.get(f"/wp/v2/posts/{post_id}", {"context": "edit"})

    def find_posts_by_slug(self, slug: str) -> list[dict[str, Any]]:
        # Every status except trash (WordPress renames trashed slugs anyway).
        return self.get_all(
            "/wp/v2/posts",
            {"slug": slug, "status": "publish,future,draft,pending,private", "context": "edit"},
        )

    def create_post(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post("/wp/v2/posts", payload)

    def update_post(self, post_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return self.post(f"/wp/v2/posts/{post_id}", payload)


def _api_error(method: str, path: str, resp: Response) -> WPPostError:
    body = resp.body if isinstance(resp.body, dict) else {}
    code = body.get("code") or "unknown_error"
    message = body.get("message") or (resp.content[:200].decode("utf-8", "replace") or "")
    summary = f"{method} {path} failed: HTTP {resp.status} {code}: {message}".strip()
    if resp.status == 401 or code in {
        "incorrect_password",
        "invalid_username",
        "invalid_email",
        "rest_not_logged_in",
        "application_passwords_disabled",
    }:
        return ConfigError(
            redact(summary),
            hint=(
                "Authentication failed. Check WP_USERNAME and WP_APPLICATION_PASSWORD; "
                "the password must be an Application Password, not your login password. "
                "Run ./bin/wp-post doctor."
            ),
        )
    if resp.status == 403:
        return RemoteError(
            redact(summary),
            hint="Your account lacks permission for this. doctor lists the capabilities it needs.",
        )
    details = None
    if body.get("data") and isinstance(body["data"], dict):
        details = redact(jsonlib.dumps(body["data"], sort_keys=True)[:1000])
    err = RemoteError(redact(summary), details=details)
    err.wp_code = code  # type: ignore[attr-defined]
    err.wp_data = body.get("data")  # type: ignore[attr-defined]
    return err
