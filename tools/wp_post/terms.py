"""Tags and categories: find existing terms case-insensitively, create the rest.

Front matter is canonical. When a post's front matter has `tags`, the post's
WordPress tags are set to exactly that list; likewise `categories`. If a key is
absent, that taxonomy is not sent at all and remote terms are left as they are.
A wp-admin change to a post's terms since the last sync is reported as a
conflict, like any other remote edit, so nothing is removed unexpectedly.
"""

from __future__ import annotations

import html
from dataclasses import dataclass

from wp_post.client import WordPressClient
from wp_post.document import slugify
from wp_post.errors import RemoteError

# WordPress.com Reader leaves posts with more than this many tags + categories
# out of its topic listings.
READER_TERM_LIMIT = 15

ENDPOINTS = {"tags": "/wp/v2/tags", "categories": "/wp/v2/categories"}


@dataclass
class TermPlan:
    taxonomy: str
    name: str
    term_id: int | None
    remote_name: str | None = None
    note: str = ""

    @property
    def create(self) -> bool:
        return self.term_id is None


class TermResolver:
    def __init__(self, client: WordPressClient):
        self.client = client
        self.warnings: list[str] = []

    def _lookup(self, taxonomy: str, name: str) -> TermPlan:
        folded, slug = name.casefold(), slugify(name)
        fields = {"per_page": 100, "_fields": "id,name,slug"}
        results = list(self.client.get(ENDPOINTS[taxonomy], {"search": name, **fields}) or [])
        # WordPress stores "&" as "&amp;" in names, so a text search can miss;
        # an exact slug lookup catches those.
        seen = {r["id"] for r in results}
        for r in self.client.get(ENDPOINTS[taxonomy], {"slug": slug, **fields}) or []:
            if r["id"] not in seen:
                results.append(r)
        matches = [
            r for r in results if html.unescape(r["name"]).casefold() == folded or r["slug"] == slug
        ]
        if not matches:
            return TermPlan(taxonomy, name, None, note="new")
        # Prefer an exact-case name match, then the oldest term.
        matches.sort(key=lambda r: (html.unescape(r["name"]) != name, r["id"]))
        best = matches[0]
        if len(matches) > 1:
            names = ", ".join(f"{html.unescape(m['name'])!r} (id {m['id']})" for m in matches)
            self.warnings.append(
                f"several existing {taxonomy} match {name!r}: {names}; using id {best['id']}"
            )
        remote_name = html.unescape(best["name"])
        note = "" if remote_name == name else f"existing term is spelled {remote_name!r}"
        return TermPlan(taxonomy, name, best["id"], remote_name, note)

    def plan(self, taxonomy: str, names: list[str]) -> list[TermPlan]:
        return [self._lookup(taxonomy, n) for n in names]

    def apply(self, plans: list[TermPlan]) -> list[int]:
        ids = []
        for p in plans:
            if p.term_id is None:
                try:
                    created = self.client.post(ENDPOINTS[p.taxonomy], {"name": p.name})
                    p.term_id = int(created["id"])
                except RemoteError as exc:
                    # Raced with another creation, or matched a term search missed.
                    data = getattr(exc, "wp_data", None) or {}
                    if getattr(exc, "wp_code", "") == "term_exists" and data.get("term_id"):
                        p.term_id = int(data["term_id"])
                    else:
                        raise
            ids.append(p.term_id)
        return ids


def combined_term_count(
    tags: list[str], categories: list[str] | None, remote_categories: int
) -> int:
    """Tags + categories as WordPress will see them. If the post does not set
    categories locally, it keeps its remote ones (or the default category)."""
    cats = len(categories) if categories is not None else max(remote_categories, 1)
    return len(tags) + cats
