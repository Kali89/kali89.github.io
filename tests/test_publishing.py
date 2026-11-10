"""End-to-end CLI behaviour against the fake WordPress."""

import json

from conftest import NOW, make_png, write_post
from wp_post.document import load_post
from wp_post.render import render

DRAFT = "_drafts/my-post.md"
POST = "_posts/2026-11-09-my-post.md"


def post_writes(fake):
    return [(r["method"], r["url"].split("/wp-json")[1]) for r in fake.writes]


def remote_from_file(fake, run, rel, **fields):
    """Create a remote post whose content matches what the file renders to."""
    post = load_post(run.repo / rel, run.repo)
    return fake.add_post(
        slug=post.slug, title=post.title, content=render(post.body, {}, post.slug), **fields
    )


# -- drafts -------------------------------------------------------------------


def test_sync_creates_draft_records_id_and_prints_urls(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"\ntags: [life]')
    code, out, err = run("sync", DRAFT)
    assert code == 0, err
    assert post_writes(fake) == [("POST", "/wp/v2/tags"), ("POST", "/wp/v2/posts")]
    sent = fake.writes[-1]["json"]
    assert sent["status"] == "draft" and sent["comment_status"] == "open"
    assert sent["slug"] == "my-post" and sent["title"] == "My Post"
    assert "<p>Hello world.</p>" in sent["content"] and "title:" not in sent["content"]
    pid = fake.posts and max(fake.posts)
    assert f"wordpress_id: {pid}" in (run.repo / DRAFT).read_text()
    assert (run.repo / f".wordpress/posts/{pid}.json").exists()
    assert f"post.php?post={pid}&action=edit" in out and "preview=true" in out


def test_resync_unchanged_file_is_a_noop(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    state_before = next((run.repo / ".wordpress/posts").iterdir()).read_text()
    n = len(fake.writes)
    code, out, _ = run("sync", DRAFT)
    assert code == 0 and "Already up to date" in out
    assert len(fake.writes) == n
    assert next((run.repo / ".wordpress/posts").iterdir()).read_text() == state_before


def test_posts_dir_file_still_syncs_as_draft(run, fake):
    write_post(run.repo, POST, 'title: "Dated"')
    code, _, _ = run("sync", POST)
    assert code == 0
    assert fake.writes[-1]["json"]["status"] == "draft"
    assert fake.writes[-1]["json"]["date"] == "2026-11-09T00:00:00"


def test_sync_updates_existing_draft_by_id_with_update_request(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    pid = max(fake.posts)
    path = run.repo / DRAFT
    path.write_text(path.read_text().replace("Hello world.", "Changed."))
    code, _, err = run("sync", DRAFT)
    assert code == 0, err
    assert post_writes(fake)[-1] == ("POST", f"/wp/v2/posts/{pid}")
    assert set(fake.writes[-1]["json"]) == {"content"}  # only what changed


def test_renamed_file_with_known_id_does_not_duplicate(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    pid = max(fake.posts)
    text = (run.repo / DRAFT).read_text().replace('"My Post"', '"My Post"\nslug: new-name')
    (run.repo / DRAFT).unlink()
    (run.repo / POST).write_text(text)
    code, out, err = run("sync", POST)
    assert code == 0, err
    assert len(fake.posts) == 1 and fake.posts[pid]["slug"] == "new-name"
    assert "moved/renamed" in out


# -- resolution ------------------------------------------------------------------


def test_slug_fallback_adopts_identical_post_without_writing(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote = remote_from_file(fake, run, POST, status="draft", date="2026-11-09T00:00:00")
    code, out, err = run("sync", POST)
    assert code == 0, err
    assert fake.writes == []
    assert f"wordpress_id: {remote['id']}" in (run.repo / POST).read_text()
    assert "matched existing post" in out


def test_slug_fallback_with_different_content_needs_force(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote = fake.add_post(
        slug="my-post",
        title="My Post",
        content="<p>imported</p>",
        status="publish",
        date="2026-11-09T00:00:00",
    )
    code, _, err = run("update", POST)
    assert code == 3 and "never been synced" in err and fake.writes == []
    code, _, err = run("update", POST, "--force")
    assert code == 0, err
    assert post_writes(fake) == [("POST", f"/wp/v2/posts/{remote['id']}")]
    assert "status" not in fake.writes[-1]["json"]


def test_ambiguous_slug_stops(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    fake.add_post(slug="my-post", status="draft")
    fake.add_post(slug="my-post", status="pending")
    code, _, err = run("sync", DRAFT)
    assert code == 7 and "refusing to guess" in err and "wordpress_id" in err
    assert fake.writes == []


def test_unknown_wordpress_id_is_not_recreated(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"\nwordpress_id: 999')
    code, _, err = run("sync", DRAFT)
    assert code == 7 and "does not exist" in err and fake.writes == []


def test_two_files_claiming_one_post_are_refused(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    pid = max(fake.posts)
    write_post(run.repo, "_drafts/copy.md", f'title: "Copy"\nwordpress_id: {pid}')
    code, _, err = run("sync", "_drafts/copy.md")
    assert code == 7 and "already linked" in err


def test_draft_whose_slug_matches_a_live_post_is_refused(run, fake):
    """The real-world case: _drafts/psychological_discomfort.md vs a published post."""
    write_post(run.repo, "_drafts/psychological_discomfort.md", 'title: "New thoughts"')
    fake.add_post(slug="psychological-discomfort", status="publish", content="<p>live</p>")
    code, _, err = run("sync", "_drafts/psychological_discomfort.md")
    assert code == 7 and "distinct `slug:`" in err and fake.writes == []


# -- published posts ---------------------------------------------------------------


def test_update_published_post_uses_update_request_and_keeps_status(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote = remote_from_file(fake, run, POST, status="publish", date="2026-11-09T00:00:00")
    run("sync", POST)  # refused (live) — but must not write
    assert fake.writes == []
    run("update", POST)  # identical: adopts, no write
    path = run.repo / POST
    path.write_text(path.read_text().replace("Hello world.", "Edited."))
    code, out, err = run("update", POST)
    assert code == 0, err
    assert post_writes(fake) == [("POST", f"/wp/v2/posts/{remote['id']}")]
    assert "status" not in fake.writes[0]["json"]
    assert fake.posts[remote["id"]]["status"] == "publish" and len(fake.posts) == 1
    assert "Public:" in out


def test_sync_and_publish_refuse_live_posts(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote_from_file(fake, run, POST, status="publish", date="2026-11-09T00:00:00")
    for cmd in ("sync", "publish"):
        code, _, err = run(cmd, POST, "--yes") if cmd == "publish" else run(cmd, POST)
        assert code == 7 and "update" in err
    assert fake.writes == []


def test_update_never_creates(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    code, _, err = run("update", POST)
    assert code == 7 and "never creates" in err and fake.writes == []


def test_live_url_change_needs_force(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote = remote_from_file(fake, run, POST, status="publish", date="2026-11-09T00:00:00")
    run("update", POST)
    path = run.repo / POST
    path.write_text(path.read_text().replace('"My Post"', '"My Post"\nslug: renamed'))
    code, _, err = run("update", POST)
    assert code == 7 and "public URL" in err and fake.writes == []
    code, _, _ = run("update", POST, "--force")
    assert code == 0 and fake.posts[remote["id"]]["slug"] == "renamed"


# -- publishing ----------------------------------------------------------------------


def test_publish_requires_typed_confirmation(run, fake):
    write_post(run.repo, POST, 'title: "My Post"\ntags: [life]')
    run.answers = ["publish"]
    code, out, err = run("publish", POST)
    assert code == 0, err
    for needle in (
        "About to PUBLISH",
        "Title:       My Post",
        "Slug:        my-post",
        "Date:        2026-11-09",
        "Tags:        life",
        "does not exist yet → publish",
        "First publication: yes",
        "email",
    ):
        assert needle in out, needle
    assert run.prompts and fake.writes[-1]["json"]["status"] == "publish"
    assert "Public:" in out


def test_publish_declined_changes_nothing(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    run.answers = ["y"]
    code, _, err = run("publish", POST)
    assert code == 8 and fake.writes == []
    assert "wordpress_id" not in (run.repo / POST).read_text()


def test_publish_without_tty_needs_yes(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    run.tty = False
    code, _, err = run("publish", POST)
    assert code == 7 and "--yes" in err and fake.writes == []
    code, _, err = run("publish", POST, "--yes")
    assert code == 0 and run.prompts == []


def test_publish_existing_draft_transitions_same_post(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    run("sync", POST)
    pid = max(fake.posts)
    code, _, _ = run("publish", POST, "--yes")
    assert code == 0
    assert post_writes(fake)[-1] == ("POST", f"/wp/v2/posts/{pid}")
    assert fake.writes[-1]["json"] == {"status": "publish"}
    assert len(fake.posts) == 1 and fake.posts[pid]["status"] == "publish"


def test_future_date_schedules(run, fake):
    write_post(run.repo, "_posts/2026-12-25-xmas.md", 'title: "Xmas"')
    code, out, _ = run("publish", "_posts/2026-12-25-xmas.md", "--yes")
    assert code == 0
    assert fake.writes[-1]["json"]["status"] == "future"
    assert "Scheduled" in out and fake.posts[max(fake.posts)]["status"] == "future"


def test_published_false_blocks_publish(run, fake):
    write_post(run.repo, POST, 'title: "My Post"\npublished: false')
    code, _, err = run("publish", POST, "--yes")
    assert code == 7 and "published: false" in err


# -- dry run -------------------------------------------------------------------------


def test_dry_run_sends_no_writes_and_changes_no_files(run, fake):
    write_post(
        run.repo, POST, 'title: "My Post"\ntags: [brand-new]', "![p](/assets/images/photo.png)\n"
    )
    before = (run.repo / POST).read_text()
    for argv in (["sync", POST, "--dry-run"], ["publish", POST, "--dry-run"]):
        code, out, err = run(*argv)
        assert code == 0, err
        assert "Dry run" in out and "will create tag: brand-new" in out
        assert "will upload image: assets/images/photo.png" in out
    assert fake.writes == [] and run.prompts == []
    assert (run.repo / POST).read_text() == before
    assert not (run.repo / ".wordpress").exists()


def test_dry_run_update_of_live_post(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    remote_from_file(fake, run, POST, status="publish", date="2026-11-09T00:00:00")
    run("update", POST)
    (run.repo / POST).write_text((run.repo / POST).read_text().replace("Hello", "Bye"))
    code, out, _ = run("update", POST, "-n")
    assert code == 0 and "will update: content" in out and fake.writes == []


# -- conflicts -----------------------------------------------------------------------


def test_remote_edit_is_a_conflict_and_force_overrides(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    pid = max(fake.posts)
    fake.admin_edit(pid, content=fake.posts[pid]["content"] + "\n<p>typo fix in wp-admin</p>")
    (run.repo / DRAFT).write_text((run.repo / DRAFT).read_text().replace("Hello", "Hi"))
    n = len(fake.writes)
    code, _, err = run("sync", DRAFT)
    assert code == 3
    assert "changed since the last sync: content" in err and "typo fix in wp-admin" in err
    assert len(fake.writes) == n
    code, _, err = run("status", DRAFT)
    assert code == 0
    code, _, err = run("sync", DRAFT, "--force")
    assert code == 0 and "--force: overwriting" in err
    assert "typo fix" not in fake.posts[pid]["content"]


def test_remote_term_change_is_a_conflict(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"\ntags: [a]')
    run("sync", DRAFT)
    pid = max(fake.posts)
    fake.admin_edit(pid, tags=fake.posts[pid]["tags"] + [555])
    code, _, err = run("sync", DRAFT)
    assert code == 3 and "tags" in err


def test_resave_without_changes_only_warns(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    fake.admin_edit(max(fake.posts))  # bumps modified only
    code, out, err = run("sync", DRAFT)
    assert code == 0 and "saved in WordPress since the last sync" in err


def test_status_is_read_only(run, fake):
    write_post(run.repo, DRAFT, 'title: "My Post"')
    run("sync", DRAFT)
    n = len(fake.writes)
    code, out, _ = run("status", DRAFT, "--diff")
    assert code == 0 and "in sync" in out and len(fake.writes) == n


# -- terms ------------------------------------------------------------------------


def test_terms_reused_case_insensitively_and_created_when_missing(run, fake):
    fake.tags[7] = {"id": 7, "name": "Python", "slug": "python"}
    fake.categories[8] = {"id": 8, "name": "Tech &amp; AI", "slug": "tech-ai"}
    write_post(
        run.repo,
        DRAFT,
        'title: "T"\ntags: [python, PYTHON, data-science]\ncategories: ["tech & ai"]',
    )
    code, _, err = run("sync", DRAFT)
    assert code == 0, err
    sent = fake.writes[-1]["json"]
    new_id = next(t["id"] for t in fake.tags.values() if t["name"] == "data-science")
    assert sent["tags"] == [7, new_id] and sent["categories"] == [8]
    assert [w["json"]["name"] for w in fake.writes if w["url"].endswith("/tags")] == [
        "data-science"
    ]


def test_without_categories_key_remote_categories_are_untouched(run, fake):
    write_post(run.repo, DRAFT, 'title: "T"\ntags: [a]')
    run("sync", DRAFT)
    assert "categories" not in fake.writes[-1]["json"]


def test_reader_term_limit(run, fake):
    tags = ", ".join(f"t{i}" for i in range(15))  # 15 tags + default category = 16
    write_post(run.repo, POST, f'title: "T"\ntags: [{tags}]')
    code, _, err = run("sync", POST)
    assert code == 0 and "Reader" in err  # drafts: warning only
    code, _, err = run("publish", POST, "--yes")
    assert code == 7 and "--allow-many-terms" in err
    code, _, err = run("publish", POST, "--yes", "--allow-many-terms")
    assert code == 0, err


# -- comments -------------------------------------------------------------------------


def test_comment_status_rules(run, fake):
    write_post(run.repo, DRAFT, 'title: "T"\ncomments: false')
    run("sync", DRAFT)
    assert fake.writes[-1]["json"]["comment_status"] == "closed"

    live = "_posts/2026-11-09-live.md"
    write_post(run.repo, live, 'title: "Live"')
    remote = remote_from_file(
        fake, run, live, status="publish", comment_status="closed", date="2026-11-09T00:00:00"
    )
    run("update", live)
    (run.repo / live).write_text((run.repo / live).read_text().replace("Hello", "Bye"))
    code, _, _ = run("update", live)
    assert code == 0 and "comment_status" not in fake.writes[-1]["json"]
    assert fake.posts[remote["id"]]["comment_status"] == "closed"


# -- images -----------------------------------------------------------------------------


def test_images_resolve_upload_once_and_rewrite(run, fake):
    (run.repo / "_drafts/img").mkdir()
    (run.repo / "_drafts/img/rel.png").write_bytes(make_png(pixel=9))
    write_post(
        run.repo,
        DRAFT,
        'title: "T"\nfeatured_image: /assets/images/photo.png',
        "![Root](/assets/images/photo.png)\n\n![Rel](img/rel.png)\n\n"
        "![Again](/assets/images/photo.png)\n\n![Ext](https://cdn.example/x.png)\n",
    )
    code, _, err = run("sync", DRAFT)
    assert code == 0, err
    uploads = [w for w in fake.writes if w["url"].endswith("/media")]
    assert len(uploads) == 2
    sent = fake.writes[-1]["json"]
    photo = next(m for m in fake.media.values() if m["source_url"].endswith("/photo.png"))
    assert f'src="{photo["source_url"]}"' in sent["content"]
    assert f'class="wp-image-{photo["id"]}"' in sent["content"]
    assert 'src="https://cdn.example/x.png"' in sent["content"]
    assert "/assets/images" not in sent["content"]
    assert sent["featured_media"] == photo["id"]
    manifest = json.loads((run.repo / ".wordpress/media.json").read_text())
    assert set(manifest["media"]) == {"assets/images/photo.png", "_drafts/img/rel.png"}
    assert "/assets/images/photo.png" in (run.repo / DRAFT).read_text()  # Markdown untouched

    # A second post using the same image does not upload it again.
    write_post(run.repo, "_drafts/other.md", 'title: "O"', "![x](../assets/images/photo.png)\n")
    run("sync", "_drafts/other.md")
    assert len([w for w in fake.writes if w["url"].endswith("/media")]) == 2


def test_changed_image_is_uploaded_again(run, fake):
    write_post(run.repo, DRAFT, 'title: "T"', "![p](/assets/images/photo.png)\n")
    run("sync", DRAFT)
    (run.repo / "assets/images/photo.png").write_bytes(make_png(pixel=200))
    code, out, _ = run("sync", DRAFT)
    assert code == 0 and "changed locally" in out
    assert len([w for w in fake.writes if w["url"].endswith("/media")]) == 2
    manifest = json.loads((run.repo / ".wordpress/media.json").read_text())
    assert manifest["media"]["assets/images/photo.png"]["previous"]
    assert not [w for w in fake.writes if w["method"] == "DELETE"]


def test_identical_remote_media_is_adopted_not_reuploaded(run, fake):
    item = fake.add_media("photo.png", (run.repo / "assets/images/photo.png").read_bytes())
    write_post(run.repo, DRAFT, 'title: "T"', "![p](/assets/images/photo.png)\n")
    code, out, _ = run("sync", DRAFT)
    assert code == 0 and f"reusing media {item['id']}" in out
    assert not [w for w in fake.writes if w["url"].endswith("/media")]
    assert f"wp-image-{item['id']}" in fake.writes[-1]["json"]["content"]


def test_missing_image_fails_before_any_request(run, fake):
    write_post(run.repo, POST, 'title: "T"\nfeatured_image: nope.jpg', "![x](/assets/gone.png)\n")
    code, _, err = run("publish", POST, "--yes")
    assert code == 5 and "assets/gone.png does not exist" in err and "featured_image" in err
    assert fake.requests == []


def test_image_with_gps_metadata_is_refused(run, fake):
    (run.repo / "assets/images/gps.png").write_bytes(make_png((b"eXIf", b"MM\x00*")))
    write_post(run.repo, DRAFT, 'title: "T"', "![x](/assets/images/gps.png)\n")
    code, _, err = run("sync", DRAFT)
    assert code == 5 and "image_metadata.py strip" in err and fake.requests == []


def test_image_outside_repo_is_refused(run, fake):
    write_post(run.repo, DRAFT, 'title: "T"', "![x](../../../etc/passwd.png)\n")
    code, _, err = run("sync", DRAFT)
    assert code == 5 and "outside the repository" in err


# -- validate / doctor / list ----------------------------------------------------------


def test_validate_all_is_offline(run, fake):
    write_post(run.repo, POST, 'title: "T"')
    write_post(run.repo, "_drafts/my_post.md", 'title: "T2"')
    write_post(run.repo, "_drafts/broken.md", "tags: [x]")
    code, out, err = run("validate", "--all")
    assert code == 5 and "title" in err and "slug 'my-post' is used by several files" in err
    assert fake.requests == []
    run.environ = {}
    code, _, _ = run("validate", POST)
    assert code == 0


def test_doctor_checks_permissions_without_writing(run, fake):
    code, out, err = run("doctor")
    assert code == 0, out + err
    assert "authenticated as 'Matt'" in out and "can publish posts" in out
    fake.capabilities["publish_posts"] = False
    code, out, _ = run("doctor")
    assert code == 4 and "missing capability publish_posts" in out
    assert fake.writes == []


def test_list_maps_remote_posts_to_files(run, fake):
    write_post(run.repo, POST, 'title: "My Post"')
    fake.add_post(slug="my-post", status="publish", title="My Post")
    fake.add_post(slug="orphan", status="draft", title="Orphan")
    code, out, _ = run("list")
    assert code == 0 and "_posts/2026-11-09-my-post.md (by slug)" in out
    assert "(no local file)" in out and fake.writes == []


def test_now_is_fixed():
    assert NOW.year == 2026
