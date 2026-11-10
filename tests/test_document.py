import datetime as dt

import pytest

from conftest import write_post
from wp_post.document import load_post, record_wordpress_id, slugify
from wp_post.errors import ValidationError


def test_parses_existing_jekyll_front_matter(repo):
    path = write_post(
        repo,
        "_posts/2026-11-12-my-post.md",
        """
        layout: post
        title: "My Post Title"
        date: 2026-11-12
        tags: [python, data-science]
    """,
        "Markdown content here.\n",
    )
    post = load_post(path, repo)
    assert post.title == "My Post Title"
    assert post.date == dt.date(2026, 11, 12)
    assert post.tags == ["python", "data-science"]
    assert post.categories is None  # not specified → remote left alone
    assert post.slug == "my-post"
    assert post.kind == "post"
    assert "layout" in post.front_matter and "---" not in post.body


def test_filename_supplies_date_and_slug(repo):
    path = write_post(repo, "_posts/2026-03-04-Some_Post Name.md", 'title: "X"')
    post = load_post(path, repo)
    assert post.date == dt.date(2026, 3, 4) and post.date_source == "filename"
    assert post.slug == "some-post-name" and post.slug_source == "filename"


def test_draft_filename_has_no_date_and_underscores_become_hyphens(repo):
    post = load_post(write_post(repo, "_drafts/what_is_the_ban_for.md", 'title: "X"'), repo)
    assert post.date is None
    assert post.slug == "what-is-the-ban-for"
    assert post.kind == "draft"


def test_front_matter_overrides_filename_with_warning(repo):
    path = write_post(
        repo,
        "_posts/2026-07-21-early.md",
        """
        title: "X"
        date: 2026-07-14
        slug: Custom Slug
    """,
    )
    post = load_post(path, repo)
    assert post.date == dt.date(2026, 7, 14)
    assert post.slug == "custom-slug"
    assert any("differs from the filename date" in w for w in post.warnings)


def test_datetime_with_offset(repo):
    post = load_post(
        write_post(
            repo,
            "_posts/2026-11-12-a.md",
            """
        title: "X"
        date: "2026-11-12 09:30:00 +0100"
    """,
        ),
        repo,
    )
    assert post.date == dt.datetime(2026, 11, 12, 9, 30, tzinfo=dt.timezone(dt.timedelta(hours=1)))


def test_all_supported_fields(repo):
    post = load_post(
        write_post(
            repo,
            "_drafts/a.md",
            """
        title: "X"
        tags: kids parenting
        categories: [Life, life, Work]
        excerpt: "Short"
        featured_image: /assets/images/photo.png
        wordpress_id: 42
        wordpress_modified: "2026-11-01T09:00:00"
        comments: false
    """,
        ),
        repo,
    )
    assert post.tags == ["kids", "parenting"]  # Jekyll splits strings on spaces
    assert post.categories == ["Life", "Work"]  # case-insensitive duplicate dropped
    assert any("'Life' and 'life'" in w for w in post.warnings)
    assert post.excerpt == "Short"
    assert post.featured_image == "/assets/images/photo.png"
    assert post.wordpress_id == 42
    assert post.wordpress_modified == "2026-11-01T09:00:00"
    assert post.comment_status == "closed"


@pytest.mark.parametrize(
    "front, needle",
    [
        ("tags: [a]", "title"),
        ('title: "X"\ndate: next tuesday', "date"),
        ('title: "X"\nwordpress_id: abc', "wordpress_id"),
        ('title: "X"\ncomment_status: maybe', "comment_status"),
        ("title: no", "title"),  # YAML reads this as False
    ],
)
def test_invalid_front_matter(repo, front, needle):
    with pytest.raises(ValidationError) as exc:
        load_post(write_post(repo, "_drafts/bad.md", front), repo)
    assert needle in exc.value.message


def test_no_front_matter(repo):
    path = repo / "_drafts/raw.md"
    path.write_text("Just text\n")
    with pytest.raises(ValidationError, match="no front matter"):
        load_post(path, repo)


def test_record_wordpress_id_preserves_everything_else(repo):
    original = (
        '---\nlayout: post\ntitle:   "Odd  spacing"   # comment\ndate: 2026-11-12\n'
        "tags: [b, a]\n---\n\nBody with --- dashes\n---\n"
    )
    path = repo / "_posts/2026-11-12-x.md"
    path.write_text(original)
    assert record_wordpress_id(path, 123) is True
    text = path.read_text()
    assert text == original.replace("tags: [b, a]\n---", "tags: [b, a]\nwordpress_id: 123\n---", 1)
    assert record_wordpress_id(path, 123) is False  # idempotent
    with pytest.raises(ValidationError, match="refusing"):
        record_wordpress_id(path, 999)


def test_record_wordpress_id_keeps_crlf(repo):
    path = repo / "_drafts/crlf.md"
    path.write_bytes(b'---\r\ntitle: "X"\r\n---\r\nBody\r\n')
    record_wordpress_id(path, 7)
    assert path.read_bytes() == b'---\r\ntitle: "X"\r\nwordpress_id: 7\r\n---\r\nBody\r\n'


def test_slugify_matches_jekyll_default():
    assert slugify("Hello, World! It's 2026") == "hello-world-it-s-2026"
    assert slugify("psychological_discomfort") == "psychological-discomfort"
