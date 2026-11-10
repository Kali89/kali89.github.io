"""Load configuration and credentials.

Sources, highest precedence first:

1. Environment variables.
2. `.wp-post.env` in the repository root (git-ignored; must be mode 600).
3. macOS Keychain, password only: service `wp-post`, account = WP_USERNAME.

There is deliberately no command-line flag for the password: argv is visible
in shell history and process listings.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlparse

import yaml

from wp_post.errors import ConfigError
from wp_post.redaction import register_secret

ENV_FILE_NAME = ".wp-post.env"
KEYCHAIN_SERVICE = "wp-post"

VARS = {
    "WP_SITE_URL": "Site URL, e.g. https://dogdogfish.com (defaults to `url` in _config.yml)",
    "WP_SITE_ID": "WordPress.com blog ID (optional; doctor cross-checks it)",
    "WP_USERNAME": "Your WordPress username (the account that owns the Application Password)",
    "WP_APPLICATION_PASSWORD": "Application Password (never your login password)",
}

KeychainLookup = Callable[[str, str], "str | None"]


@dataclass(frozen=True)
class Config:
    site_url: str
    site_id: str | None
    username: str | None
    password: str | None = field(repr=False)
    sources: dict[str, str] = field(default_factory=dict)
    env_file: Path | None = None

    @property
    def has_credentials(self) -> bool:
        return bool(self.username and self.password)

    def edit_url(self, post_id: int) -> str:
        return f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit"


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines. Supports comments, `export`, and simple quoting."""
    values: dict[str, str] = {}
    for lineno, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        line = line.removeprefix("export ").strip()
        if "=" not in line:
            raise ConfigError(
                f"{path.name}:{lineno}: expected KEY=VALUE",
                hint="See wp-post.env.example for the format.",
            )
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key] = value
    return values


def env_file_problems(path: Path) -> list[str]:
    """Return warnings about an env file's permissions (it holds a secret)."""
    if sys.platform == "win32" or not path.exists():
        return []
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return [f"{path.name} is readable by other users (mode {mode:o}); run: chmod 600 {path}"]
    return []


def keychain_lookup(service: str, account: str) -> str | None:
    """Read a generic password from the macOS Keychain. The secret travels on the
    child's stdout, never argv. Returns None when unavailable."""
    if sys.platform != "darwin":
        return None
    try:
        proc = subprocess.run(
            ["/usr/bin/security", "find-generic-password", "-s", service, "-a", account, "-w"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    value = proc.stdout.rstrip("\n")
    return value or None


def site_url_from_jekyll(repo_root: Path) -> str | None:
    cfg = repo_root / "_config.yml"
    if not cfg.exists():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return None
    url = data.get("url")
    return str(url) if url else None


def normalise_site_url(url: str) -> str:
    url = url.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ConfigError(
            f"WP_SITE_URL must be an https:// URL, got {url!r}",
            hint="Credentials are sent with every request, so plain http is refused.",
        )
    if parsed.path not in ("", "/"):
        raise ConfigError(f"WP_SITE_URL should be the site root, got {url!r}")
    return f"https://{parsed.netloc}"


def load_config(
    repo_root: Path,
    environ: Mapping[str, str] | None = None,
    keychain: KeychainLookup | None = keychain_lookup,
) -> Config:
    environ = os.environ if environ is None else environ
    env_path = repo_root / ENV_FILE_NAME
    file_values = parse_env_file(env_path) if env_path.exists() else {}

    sources: dict[str, str] = {}

    def pick(name: str) -> str | None:
        if environ.get(name):
            sources[name] = "environment"
            return environ[name]
        if file_values.get(name):
            sources[name] = ENV_FILE_NAME
            return file_values[name]
        return None

    site_url = pick("WP_SITE_URL")
    if not site_url:
        site_url = site_url_from_jekyll(repo_root)
        if site_url:
            sources["WP_SITE_URL"] = "_config.yml"
    if not site_url:
        raise ConfigError(
            "WP_SITE_URL is not set",
            hint=f"Set it in the environment or in {ENV_FILE_NAME} (see wp-post.env.example).",
        )

    username = pick("WP_USERNAME")
    password = pick("WP_APPLICATION_PASSWORD")
    if not password and username and keychain is not None:
        password = keychain(KEYCHAIN_SERVICE, username)
        if password:
            sources["WP_APPLICATION_PASSWORD"] = f"macOS Keychain (service {KEYCHAIN_SERVICE})"
    register_secret(password)

    site_id = pick("WP_SITE_ID")
    if site_id and not re.fullmatch(r"\d+", site_id):
        raise ConfigError(f"WP_SITE_ID must be numeric, got {site_id!r}")

    return Config(
        site_url=normalise_site_url(site_url),
        site_id=site_id,
        username=username,
        password=password,
        sources=sources,
        env_file=env_path if env_path.exists() else None,
    )


def require_credentials(cfg: Config) -> None:
    missing = [
        name
        for name, value in (
            ("WP_USERNAME", cfg.username),
            ("WP_APPLICATION_PASSWORD", cfg.password),
        )
        if not value
    ]
    if missing:
        raise ConfigError(
            f"missing credentials: {', '.join(missing)}",
            hint=(
                "Run ./bin/wp-post doctor --setup, or see "
                "docs/wordpress-publishing.md#authentication."
            ),
        )
