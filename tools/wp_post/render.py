"""Markdown → WordPress post content.

Approach: render Markdown to semantic HTML with markdown-it-py (CommonMark plus
tables, strikethrough and footnotes), then wrap each top-level element in
Gutenberg block delimiters:

- paragraphs        → core/paragraph  (`<p>…</p>`: trivially stable markup)
- headings          → core/heading
- `<!--more-->`     → core/more       (split out even when it ends a paragraph)
- everything else   → core/html       (lists, quotes, code, tables, images,
                                        raw HTML, footnotes, rules)

The core/html wrapper renders the HTML exactly as given and never trips the
block editor's validation. Native blocks for lists, images or code would make
wp-admin editing nicer, but their saved markup changes between WordPress
releases. Markdown is canonical, so we choose the stable representation.

Output is a pure function of (Markdown, media map, slug): unchanged input
produces byte-identical content, so re-syncing an unchanged file is a no-op.
"""

from __future__ import annotations

import html
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token
from mdit_py_plugins.footnote import footnote_plugin

MORE_RE = re.compile(r"^<!--\s*more\s*-->$", re.IGNORECASE)
IMG_SRC_RE = re.compile(r"(<img\b[^>]*?\bsrc\s*=\s*)([\"'])(.*?)\2", re.IGNORECASE | re.DOTALL)
BLOCK_DELIMITER_RE = re.compile(r"<!--\s*/?wp:")


@dataclass(frozen=True)
class MediaRef:
    id: int | None
    url: str


@dataclass(frozen=True)
class ImageRef:
    src: str
    alt: str
    origin: str  # "markdown" or "html"


def _markdown() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True, "typographer": False, "linkify": False})
    md.enable(["table", "strikethrough"])
    md.use(footnote_plugin)
    # A soft line break is just whitespace. Emitting a space rather than "\n"
    # keeps wrapped Markdown from leaking line structure into WordPress.
    md.add_render_rule("softbreak", lambda self, tokens, idx, options, env: " ")
    # Leave quotes literal in text so WordPress's wptexturize can curl them, as
    # kramdown's smart quotes did under Jekyll. (Attributes are still escaped.)
    md.add_render_rule(
        "text", lambda self, tokens, idx, options, env: html.escape(tokens[idx].content, False)
    )
    return md


_MD = _markdown()


def _walk(tokens: Iterable[Token]) -> Iterable[Token]:
    for tok in tokens:
        yield tok
        if tok.children:
            yield from _walk(tok.children)


def find_images(body: str) -> list[ImageRef]:
    """All image references in a Markdown body, in document order."""
    refs = []
    for tok in _walk(_MD.parse(body, {})):
        if tok.type == "image":
            refs.append(ImageRef(str(tok.attrGet("src") or ""), tok.content, "markdown"))
        elif tok.type in ("html_block", "html_inline"):
            for m in IMG_SRC_RE.finditer(tok.content):
                refs.append(ImageRef(html.unescape(m.group(3)), "", "html"))
    return refs


def has_block_delimiters(body: str) -> bool:
    return bool(BLOCK_DELIMITER_RE.search(body))


def _block(name: str, inner: str, attrs: dict | None = None) -> str:
    attr = f" {json.dumps(attrs, sort_keys=True, separators=(',', ':'))}" if attrs else ""
    return f"<!-- wp:{name}{attr} -->\n{inner}\n<!-- /wp:{name} -->"


MORE_BLOCK = _block("more", "<!--more-->")


class _Renderer:
    def __init__(self, media: Mapping[str, MediaRef], doc_id: str):
        self.media = media
        self.env: dict = {"docId": doc_id} if doc_id else {}

    def _rewrite_html(self, content: str) -> str:
        def sub(m: re.Match) -> str:
            ref = self.media.get(html.unescape(m.group(3)))
            if ref is None:
                return m.group(0)
            return f"{m.group(1)}{m.group(2)}{html.escape(ref.url, quote=True)}{m.group(2)}"

        return IMG_SRC_RE.sub(sub, content)

    def _prepare(self, tokens: list[Token]) -> None:
        for tok in _walk(tokens):
            if tok.type == "image":
                # Alt text wrapped across lines in the Markdown: collapse to spaces.
                for child in tok.children or []:
                    if child.type in ("softbreak", "hardbreak"):
                        child.type, child.content = "text", " "
                ref = self.media.get(str(tok.attrGet("src") or ""))
                if ref is not None:
                    tok.attrSet("src", ref.url)
                    if ref.id:
                        tok.attrSet("class", f"wp-image-{ref.id}")
            elif tok.type in ("html_block", "html_inline"):
                tok.content = self._rewrite_html(tok.content)

    def inline(self, children: list[Token]) -> str:
        return _MD.renderer.renderInline(children, _MD.options, self.env).strip()

    def paragraph(self, inline: Token) -> list[str]:
        children = list(inline.children or [])
        out: list[str] = []
        segment: list[Token] = []

        def flush() -> None:
            if segment:
                rendered = self.figure(segment) or self._para(segment)
                if rendered:
                    out.append(rendered)
            segment.clear()

        for child in children:
            if child.type == "html_inline" and MORE_RE.match(child.content.strip()):
                flush()
                out.append(MORE_BLOCK)
            else:
                segment.append(child)
        flush()
        return out

    def _para(self, children: list[Token]) -> str | None:
        text = self.inline(children)
        return _block("paragraph", f"<p>{text}</p>") if text else None

    def figure(self, children: list[Token]) -> str | None:
        """A paragraph holding only an image (optionally linked) becomes a figure.
        The image's Markdown title, if any, becomes the caption."""
        significant = [
            c for c in children if not (c.type in ("softbreak", "text") and not c.content.strip())
        ]
        types = [c.type for c in significant]
        if types not in (["image"], ["link_open", "image", "link_close"]):
            return None
        img = next(c for c in significant if c.type == "image")
        caption = img.attrGet("title")
        if caption:
            img.attrs.pop("title", None)
        inner = self.inline(significant)
        if caption:
            inner += (
                f'<figcaption class="wp-element-caption">{html.escape(str(caption))}</figcaption>'
            )
        return _block("html", f'<figure class="wp-block-image">{inner}</figure>')

    def render(self, body: str) -> str:
        tokens = _MD.parse(body, self.env)
        self._prepare(tokens)
        blocks: list[str] = []
        i = 0
        while i < len(tokens):
            tok = tokens[i]
            j = i
            if tok.nesting == 1:
                depth = 0
                while True:
                    depth += tokens[j].nesting
                    if depth == 0:
                        break
                    j += 1
            group = tokens[i : j + 1]
            i = j + 1

            if tok.type == "paragraph_open" and len(group) == 3:
                blocks.extend(self.paragraph(group[1]))
            elif tok.type == "heading_open":
                level = int(tok.tag[1])
                text = self.inline(group[1].children or [])
                attrs = {"level": level} if level != 2 else None
                inner = f'<h{level} class="wp-block-heading">{text}</h{level}>'
                blocks.append(_block("heading", inner, attrs))
            elif tok.type == "html_block" and MORE_RE.match(tok.content.strip()):
                blocks.append(MORE_BLOCK)
            else:
                rendered = _MD.renderer.render(group, _MD.options, self.env).strip()
                if tok.type in ("fence", "code_block"):
                    rendered = rendered.replace("<pre>", '<pre class="wp-block-code">', 1)
                if rendered:
                    blocks.append(_block("html", rendered))
        return "\n\n".join(blocks) + "\n" if blocks else ""


def render(body: str, media: Mapping[str, MediaRef] | None = None, doc_id: str = "") -> str:
    """Render a Markdown body (no front matter) to WordPress block content.

    `media` maps image src strings, exactly as written in the Markdown, to
    uploaded media. Unmapped images (external URLs) are left untouched.
    `doc_id` namespaces footnote anchors so two posts on one page cannot clash.
    """
    return _Renderer(media or {}, doc_id).render(body)
