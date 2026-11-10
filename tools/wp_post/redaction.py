"""Keep credentials out of anything we print.

Every secret loaded at runtime is registered here, and all CLI output passes
through `redact()`. This is a second line of defence: the code also never
formats credentials into messages in the first place.
"""

from __future__ import annotations

import base64

REDACTED = "[REDACTED]"
_secrets: set[str] = set()


def register_secret(value: str | None) -> None:
    if not value or len(value) < 4:
        return
    _secrets.add(value)
    # Application Passwords are displayed with spaces but accepted without.
    compact = value.replace(" ", "")
    if len(compact) >= 4:
        _secrets.add(compact)


def register_basic_auth(username: str, password: str) -> str:
    """Register the password and the derived Basic token; return the header value."""
    register_secret(password)
    token = base64.b64encode(f"{username}:{password}".encode()).decode("ascii")
    register_secret(token)
    return f"Basic {token}"


def redact(text: object) -> str:
    out = str(text)
    for secret in sorted(_secrets, key=len, reverse=True):
        out = out.replace(secret, REDACTED)
    return out


def clear_secrets() -> None:
    """For tests."""
    _secrets.clear()
