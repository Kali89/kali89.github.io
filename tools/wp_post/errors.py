"""Exception types. Each carries the process exit status the CLI returns."""

from __future__ import annotations


class WPPostError(Exception):
    """Base class: a failure with a user-facing message and an optional hint."""

    exit_code = 1

    def __init__(self, message: str, *, hint: str | None = None, details: str | None = None):
        super().__init__(message)
        self.message = message
        self.hint = hint
        self.details = details


class ConflictError(WPPostError):
    """The remote post changed in a way we did not cause. Resolve, or use --force."""

    exit_code = 3


class ConfigError(WPPostError):
    """Missing/invalid configuration or failed authentication."""

    exit_code = 4


class ValidationError(WPPostError):
    """A local file is invalid (front matter, missing image, unsafe metadata...)."""

    exit_code = 5


class RemoteError(WPPostError):
    """WordPress returned an error, or the network failed."""

    exit_code = 6


class RefusedError(WPPostError):
    """A safety rule stopped the operation (wrong command for the post's state, etc.)."""

    exit_code = 7


class AbortedError(WPPostError):
    """The user declined a confirmation prompt."""

    exit_code = 8


EXIT_CODES = {
    0: "success",
    1: "unexpected error",
    2: "usage error (bad arguments)",
    3: "conflict: the remote post changed since the last sync",
    4: "configuration or authentication problem",
    5: "local validation failed",
    6: "WordPress API or network error",
    7: "refused by a safety rule",
    8: "aborted at a confirmation prompt",
}
