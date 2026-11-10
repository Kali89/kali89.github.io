import textwrap

from conftest import write_post
from wp_post.document import load_post
from wp_post.render import MediaRef, find_images, render


def r(md: str, media=None, doc_id="") -> str:
    return render(textwrap.dedent(md), media or {}, doc_id)


def test_paragraphs_and_headings_are_native_blocks():
    out = r("""
        Intro *text* with `code <b>`.

        ## Second level

        ### Third level
    """)
    assert out.startswith(
        "<!-- wp:paragraph -->\n<p>Intro <em>text</em> with "
        "<code>code &lt;b&gt;</code>.</p>\n<!-- /wp:paragraph -->"
    )
    assert '<!-- wp:heading -->\n<h2 class="wp-block-heading">Second level</h2>' in out
    assert '<!-- wp:heading {"level":3} -->\n<h3 class="wp-block-heading">Third level</h3>' in out


def test_more_tag_inline_at_paragraph_end_is_split_out():
    out = r("First para ends here!<!--more-->\n\nNext.\n")
    assert out == (
        "<!-- wp:paragraph -->\n<p>First para ends here!</p>\n<!-- /wp:paragraph -->\n\n"
        "<!-- wp:more -->\n<!--more-->\n<!-- /wp:more -->\n\n"
        "<!-- wp:paragraph -->\n<p>Next.</p>\n<!-- /wp:paragraph -->\n"
    )


def test_more_tag_on_its_own_line():
    assert "<!-- wp:more -->" in r("A\n\n<!--more-->\n\nB\n")


def test_soft_breaks_become_spaces_and_quotes_stay_literal():
    out = r('He said "hi"\nand it\'s fine.\n')
    assert '<p>He said "hi" and it\'s fine.</p>' in out


def test_lists_quotes_rules_go_in_html_blocks():
    out = r("""
        - one
        - two

        1. first

        > quoted **bold**

        ---
    """)
    assert "<!-- wp:html -->\n<ul>\n<li>one</li>\n<li>two</li>\n</ul>\n<!-- /wp:html -->" in out
    assert "<ol>\n<li>first</li>\n</ol>" in out
    assert "<blockquote>\n<p>quoted <strong>bold</strong></p>\n</blockquote>" in out
    assert "<hr />" in out


def test_fenced_code_keeps_language_and_escapes():
    out = r("""
        ```python
        if a < b:
            print("x")
        ```
    """)
    assert (
        '<pre class="wp-block-code"><code class="language-python">if a &lt; b:\n'
        "    print(&quot;x&quot;)\n</code></pre>"
    ) in out


def test_tables_and_footnotes():
    out = r(
        """
        | a | b |
        |---|---|
        | 1 | 2 |

        Claim.[^1]

        [^1]: Source.
    """,
        doc_id="my-post",
    )
    assert "<table>" in out and "<td>1</td>" in out
    assert 'id="fn-my-post-1"' in out  # namespaced so posts on one page cannot clash
    assert '<section class="footnotes">' in out


def test_raw_html_passes_through_with_local_src_rewritten():
    md = """
        <figure class="figure-pair">
          <img src="/assets/images/a.png" alt="A">
          <img src="https://cdn.example/b.png" alt="B">
        </figure>

        Text with <sup>TM</sup>.
    """
    out = r(md, {"/assets/images/a.png": MediaRef(5, "https://blog.example/u/a.png")})
    assert '<img src="https://blog.example/u/a.png" alt="A">' in out
    assert '<img src="https://cdn.example/b.png" alt="B">' in out
    assert '<figure class="figure-pair">' in out
    assert "<p>Text with <sup>TM</sup>.</p>" in out


def test_standalone_image_becomes_figure_with_caption():
    md = '![A cat\non a mat](/assets/images/cat.jpg "The cat")\n'
    out = r(md, {"/assets/images/cat.jpg": MediaRef(9, "https://blog.example/u/cat.jpg")})
    assert out == (
        '<!-- wp:html -->\n<figure class="wp-block-image">'
        '<img src="https://blog.example/u/cat.jpg" alt="A cat on a mat" class="wp-image-9" />'
        '<figcaption class="wp-element-caption">The cat</figcaption></figure>\n'
        "<!-- /wp:html -->\n"
    )


def test_external_image_unchanged_and_inline_image_stays_inline():
    out = r("See ![x](https://example.com/x.png) here.\n")
    assert '<p>See <img src="https://example.com/x.png" alt="x" /> here.</p>' in out


def test_find_images_covers_markdown_and_html_but_not_code():
    refs = find_images(
        textwrap.dedent("""
        ![a](one.png)

        <img src="/two.png">

        `![no](three.png)`

            ![no](four.png)
    """)
    )
    assert [(i.src, i.origin) for i in refs] == [("one.png", "markdown"), ("/two.png", "html")]


def test_output_is_deterministic_and_excludes_front_matter(repo):
    path = write_post(
        repo,
        "_posts/2026-01-01-a.md",
        """
        layout: post
        title: "Secret Title"
        tags: [x]
    """,
        "Body *here*.<!--more-->\n\n- a\n- b\n",
    )
    post = load_post(path, repo)
    a, b = render(post.body, {}, post.slug), render(post.body, {}, post.slug)
    assert a == b
    assert "Secret Title" not in a and "layout" not in a


def test_real_post_samples_render(repo):
    """Smoke-test the constructs the existing posts use."""
    body = textwrap.dedent("""
        I don't have time<sup>\\*</sup>. A [link](https://example.com "t") and **bold**.

        <sup>\\*And some of the studies were on rats.</sup>
    """)
    out = render(body)
    assert "time<sup>*</sup>." in out
    assert '<a href="https://example.com" title="t">link</a>' in out
    assert "<p><sup>*And some of the studies were on rats.</sup></p>" in out
