"""Console output. Everything printed goes through redaction."""

from __future__ import annotations

import sys
from typing import TextIO

from wp_post.redaction import redact


class Console:
    def __init__(self, out: TextIO | None = None, err: TextIO | None = None):
        self.out = out or sys.stdout
        self.err = err or sys.stderr

    def say(self, msg: str = "") -> None:
        print(redact(msg), file=self.out)

    def warn(self, msg: str) -> None:
        print(redact(f"warning: {msg}"), file=self.err)

    def error(self, msg: str) -> None:
        print(redact(f"error: {msg}"), file=self.err)

    def detail(self, msg: str) -> None:
        print(redact(msg), file=self.err)
