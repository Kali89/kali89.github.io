"""Offline checks: front matter, images, Reader term limit, slug/id collisions.

Needs no credentials and never contacts WordPress, so CI can run it.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from wp_post.document import Post, load_post
from wp_post.errors import ValidationError
from wp_post.media import collect_images
from wp_post.render import has_block_delimiters, render
from wp_post.terms import READER_TERM_LIMIT, combined_term_count


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    checked: int = 0


def validate_files(paths: list[Path], repo_root: Path) -> Report:
    report = Report()
    posts: list[Post] = []
    for path in paths:
        report.checked += 1
        try:
            post = load_post(path, repo_root)
            if has_block_delimiters(post.body):
                raise ValidationError(f"{post.rel_path}: body contains <!-- wp:... --> comments")
            collect_images(post, repo_root)
            render(post.body, {}, post.slug)  # must not raise
        except ValidationError as exc:
            report.errors.append(exc.message)
            continue
        posts.append(post)
        for w in post.warnings:
            report.warnings.append(f"{post.rel_path}: {w}")
        n = combined_term_count(post.tags, post.categories, 1)
        if n > READER_TERM_LIMIT:
            report.warnings.append(
                f"{post.rel_path}: {n} tags+categories (> {READER_TERM_LIMIT}); publish/update "
                f"will refuse without --allow-many-terms"
            )

    by_id: dict[int, list[str]] = defaultdict(list)
    by_slug: dict[str, list[Post]] = defaultdict(list)
    for p in posts:
        if p.wordpress_id:
            by_id[p.wordpress_id].append(p.rel_path)
        by_slug[p.slug].append(p)
    for wp_id, files in sorted(by_id.items()):
        if len(files) > 1:
            report.errors.append(
                f"wordpress_id {wp_id} is claimed by several files: {', '.join(files)}"
            )
    for slug, group in sorted(by_slug.items()):
        if len(group) > 1:
            files = ", ".join(p.rel_path for p in group)
            report.warnings.append(
                f"slug {slug!r} is used by several files: {files}. A file without "
                f"wordpress_id is matched by slug, so set a distinct `slug:` on any that are "
                f"different posts"
            )
    return report
