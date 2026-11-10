"""`wp-post doctor`: check configuration, authentication and permissions.

Read-only: it sends GET requests only and never creates, edits or publishes.
`--setup` interactively stores credentials (Keychain or .wp-post.env) first.
"""

from __future__ import annotations

import getpass
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

from wp_post.client import WordPressClient
from wp_post.config import (
    ENV_FILE_NAME,
    KEYCHAIN_SERVICE,
    Config,
    KeychainLookup,
    env_file_problems,
    load_config,
    parse_env_file,
)
from wp_post.errors import ConfigError, WPPostError
from wp_post.ui import Console

REQUIRED_CAPS = {
    "edit_posts": "create and edit your posts",
    "publish_posts": "publish posts",
    "edit_published_posts": "update posts that are already live",
    "upload_files": "upload images to the media library",
    "manage_categories": "create new categories",
}


def app_password_instructions(site_url: str) -> str:
    return (
        "Create an Application Password (it can be revoked at any time without "
        "touching your login):\n"
        f"  1. Open {site_url}/wp-admin/authorize-application.php?app_name=wp-post\n"
        f"     (or {site_url}/wp-admin/profile.php → Application Passwords).\n"
        "  2. Approve it. WordPress shows the password once; copy it.\n"
        "  3. Run ./bin/wp-post doctor --setup and paste it at the hidden prompt."
    )


class Doctor:
    def __init__(
        self,
        repo_root: Path,
        console: Console,
        session: Any = None,
        environ: Mapping[str, str] | None = None,
        keychain: KeychainLookup | None = None,
    ):
        self.repo_root = repo_root
        self.c = console
        self.session = session
        self.environ = environ
        self.keychain = keychain
        self.failures = 0

    def ok(self, msg: str) -> None:
        self.c.say(f"  ok    {msg}")

    def bad(self, msg: str, hint: str | None = None) -> None:
        self.failures += 1
        self.c.say(f"  FAIL  {msg}")
        if hint:
            for line in hint.splitlines():
                self.c.say(f"        {line}")

    def note(self, msg: str) -> None:
        self.c.say(f"  warn  {msg}")

    def run(self) -> int:
        c = self.c
        c.say("wp-post doctor (read-only: nothing is created, changed or published)\n")
        c.say("Configuration")
        try:
            cfg = load_config(self.repo_root, self.environ, self.keychain)
        except ConfigError as exc:
            self.bad(exc.message, exc.hint)
            return 4
        self.ok(f"site: {cfg.site_url} (from {cfg.sources.get('WP_SITE_URL')})")
        for name in ("WP_SITE_ID", "WP_USERNAME", "WP_APPLICATION_PASSWORD"):
            src = cfg.sources.get(name)
            if name == "WP_USERNAME" and cfg.username:
                self.ok(f"{name}: {cfg.username} (from {src})")
            elif name == "WP_APPLICATION_PASSWORD" and cfg.password:
                self.ok(f"{name}: set, {len(cfg.password.replace(' ', ''))} chars (from {src})")
            elif name == "WP_SITE_ID" and cfg.site_id:
                self.ok(f"{name}: {cfg.site_id} (from {src})")
            elif name != "WP_SITE_ID":
                self.bad(
                    f"{name} is not set",
                    app_password_instructions(cfg.site_url)
                    if name == "WP_APPLICATION_PASSWORD"
                    else None,
                )
        if cfg.env_file:
            for problem in env_file_problems(cfg.env_file):
                self.bad(problem)
            if not self._git_ignored(ENV_FILE_NAME):
                self.bad(f"{ENV_FILE_NAME} is NOT git-ignored", "Add it to .gitignore now.")
            else:
                self.ok(f"{ENV_FILE_NAME} is git-ignored")

        c.say("\nSite and API")
        client = WordPressClient(
            cfg.site_url, cfg.username, cfg.password, session=self.session, read_only=True
        )
        if not self._check_site(client, cfg):
            return 6
        if not cfg.has_credentials:
            c.say("\nSkipping authenticated checks until credentials are configured.")
            return 4

        c.say("\nAuthentication and permissions")
        code = self._check_auth(client, cfg)
        c.say("")
        if self.failures:
            c.say(f"{self.failures} problem(s) found.")
            return code or 4
        c.say("All checks passed. You can sync drafts; nothing was changed by doctor.")
        return 0

    def _git_ignored(self, rel: str) -> bool:
        try:
            proc = subprocess.run(
                ["git", "check-ignore", "-q", rel],
                cwd=self.repo_root,
                capture_output=True,
                check=False,
            )
        except OSError:
            return False
        return proc.returncode == 0

    def _check_site(self, client: WordPressClient, cfg: Config) -> bool:
        try:
            root = client.get("/", auth=False) or {}
        except WPPostError as exc:
            self.bad(f"could not read {cfg.site_url}/wp-json/: {exc.message}", exc.hint)
            return False
        self.ok(f"REST API reachable: {root.get('name')!r} at {root.get('url')}")
        if "wp/v2" not in (root.get("namespaces") or []):
            self.bad("the wp/v2 namespace is missing from the REST API index")
            return False
        self.ok("wp/v2 namespace available")
        if "application-passwords" in (root.get("authentication") or {}):
            self.ok("site advertises Application Password authentication")
        else:
            self.bad(
                "site does not advertise Application Passwords",
                "They may be disabled by a plugin or host policy; see the docs' fallback.",
            )
        if cfg.site_id:
            try:
                info = (
                    client.get(
                        f"https://public-api.wordpress.com/rest/v1.1/sites/{cfg.site_id}",
                        {"fields": "ID,URL"},
                        auth=False,
                    )
                    or {}
                )
                url = str(info.get("URL", "")).rstrip("/").replace("http://", "https://")
                if url == cfg.site_url:
                    self.ok(f"WP_SITE_ID {cfg.site_id} is {url}")
                else:
                    self.bad(
                        f"WP_SITE_ID {cfg.site_id} belongs to {url or 'an unknown site'}, "
                        f"not {cfg.site_url}"
                    )
            except WPPostError as exc:
                self.note(f"could not cross-check WP_SITE_ID: {exc.message}")
        return True

    def _check_auth(self, client: WordPressClient, cfg: Config) -> int:
        try:
            me = client.get("/wp/v2/users/me", {"context": "edit"}) or {}
        except WPPostError as exc:
            self.bad(exc.message, exc.hint)
            return exc.exit_code
        self.ok(
            f"authenticated as {me.get('name')!r} (user {me.get('id')}, roles: "
            f"{', '.join(me.get('roles') or []) or 'unknown'})"
        )
        caps = me.get("capabilities") or {}
        for cap, why in REQUIRED_CAPS.items():
            if caps.get(cap):
                self.ok(f"can {why} ({cap})")
            else:
                self.bad(f"missing capability {cap}: cannot {why}")
        if not caps.get("unfiltered_html"):
            self.note(
                "no unfiltered_html capability: WordPress may strip some raw HTML "
                "(e.g. iframes) from posts"
            )
        for path, what in (
            ("/wp/v2/posts", "draft posts"),
            ("/wp/v2/tags", "tags"),
            ("/wp/v2/media", "media library"),
        ):
            params: dict[str, Any] = {"per_page": 1, "context": "edit"}
            if path == "/wp/v2/posts":
                params["status"] = "draft"
            try:
                client.get(path, params)
                self.ok(f"can read {what} in edit context")
            except WPPostError as exc:
                self.bad(f"cannot read {what}: {exc.message}")
        return 0


def setup(
    repo_root: Path,
    console: Console,
    *,
    input_fn: Callable[[str], str] = input,
    getpass_fn: Callable[[str], str] = getpass.getpass,
    isatty: Callable[[], bool],
) -> None:
    """Interactively store credentials. The secret goes to a hidden prompt (or
    straight to the Keychain's own prompt), never to argv or the screen."""
    if not isatty():
        raise ConfigError("doctor --setup is interactive; run it in a terminal")
    c = console
    env_path = repo_root / ENV_FILE_NAME
    existing = parse_env_file(env_path) if env_path.exists() else {}
    try:
        site_default = load_config(repo_root, {}, None).site_url
    except ConfigError:
        site_default = "https://dogdogfish.com"
    c.say(app_password_instructions(site_default) + "\n")
    site = input_fn(f"Site URL [{site_default}]: ").strip() or site_default
    user_default = existing.get("WP_USERNAME", "")
    username = input_fn(f"WordPress username [{user_default}]: ").strip() or user_default
    if not username:
        raise ConfigError("a username is required")

    use_keychain = False
    if sys.platform == "darwin":
        answer = input_fn("Store the password in the macOS Keychain (recommended)? [Y/n]: ")
        use_keychain = answer.strip().lower() in ("", "y", "yes")

    values = dict(existing, WP_SITE_URL=site, WP_USERNAME=username)
    if use_keychain:
        c.say(
            f"\nThe Keychain will now prompt for the password (service {KEYCHAIN_SERVICE}, "
            f"account {username}). Paste the Application Password twice."
        )
        proc = subprocess.run(
            [
                "/usr/bin/security",
                "add-generic-password",
                "-U",
                "-s",
                KEYCHAIN_SERVICE,
                "-a",
                username,
                "-l",
                "wp-post Application Password",
                "-w",
            ],
            check=False,
        )
        if proc.returncode != 0:
            raise ConfigError("storing the password in the Keychain failed")
        values.pop("WP_APPLICATION_PASSWORD", None)
    else:
        secret = getpass_fn("Application Password (input hidden): ").strip()
        if not secret:
            raise ConfigError("no password entered")
        values["WP_APPLICATION_PASSWORD"] = secret

    lines = ["# wp-post local configuration. Git-ignored. Never commit this file.\n"]
    lines += [f"{k}={v}\n" for k, v in values.items()]
    fd = os.open(env_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.writelines(lines)
    os.chmod(env_path, 0o600)
    c.say(f"\nWrote {ENV_FILE_NAME} (mode 600). Running checks...\n")
