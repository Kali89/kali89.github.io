# Publishing to WordPress with `wp-post`

This repository is the **canonical source** for post content.
[dogdogfish.com](https://dogdogfish.com) is a WordPress.com (Atomic) site that
**renders and distributes** it: theme, comments, Likes, Reader, subscriptions,
newsletter emails and stats. `./bin/wp-post` moves Markdown from here to there,
and never moves anything back.

- [Daily workflow](#daily-workflow)
- [1. Architecture and source of truth](#1-architecture-and-source-of-truth)
- [2. Authentication](#authentication)
- [3. Installation](#3-installation)
- [4–8. Write, sync, preview, publish, update](#4-writing-a-draft-in-vim)
- [9. Scheduling](#9-scheduling)
- [10. Tags, categories and Reader](#10-tags-categories-and-reader)
- [11. Newsletter implications](#11-newsletter-implications)
- [12. Comments](#12-comments)
- [13. WordPress.com Likes](#13-wordpresscom-likes)
- [14. Subscriptions and the Subscribe block](#14-subscriptions-and-the-subscribe-block)
- [15. Images and featured images](#15-images-and-featured-images)
- [16. Conflicts](#16-conflicts)
- [17. Credential rotation](#17-credential-rotation)
- [18. Troubleshooting and recovery](#18-troubleshooting-and-recovery)
- [19. Revoking publishing access immediately](#19-revoking-publishing-access-immediately)
- [Reference](#reference)

## Daily workflow

```sh
vim _drafts/my-post.md                       # write
./bin/wp-post sync _drafts/my-post.md        # create/update the WordPress draft; prints a preview URL
# ...edit, sync again, preview again...

git mv _drafts/my-post.md _posts/2026-11-12-my-post.md   # date it when ready
./bin/wp-post publish _posts/2026-11-12-my-post.md       # summary + type "publish" to confirm

git add -A && git commit -m "My post"        # commit the post *and* .wordpress/
```

Fixing a typo in something already live:

```sh
vim _posts/2026-11-12-my-post.md
./bin/wp-post update _posts/2026-11-12-my-post.md --dry-run   # see what would change
./bin/wp-post update _posts/2026-11-12-my-post.md
```

Commits and pushes never publish anything. CI only runs checks.

## 1. Architecture and source of truth

```
 _drafts/*.md, _posts/*.md ──► wp-post ──► WordPress REST API (wp/v2) ──► dogdogfish.com
        (canonical)           (this repo)    Application Password auth      Reader, email, Likes, comments
```

| Owned by Git (Markdown) | Owned by WordPress |
|---|---|
| title, body, slug, date, excerpt | comments, Likes, subscribers, stats |
| tags and categories (when set in front matter) | site settings, theme, Subscribe block |
| featured image, comment status (when set) | post status after publication |

Rules the tool enforces:

- **Nothing goes live without an explicit `publish`.** `sync` only ever creates or
  updates drafts. Putting a file in `_posts/` does not publish it. Neither does
  a commit, a push, or CI.
- **`update` changes a post in place.** It never creates a post, never changes
  its status, and never deletes and recreates anything.
- **wp-admin edits are never silently overwritten.** If the post changed in
  WordPress since the last sync, wp-post stops with a conflict. `--force` is the
  deliberate override.
- **There is no remote → local merge.** wp-post never edits your Markdown, except
  to insert one `wordpress_id:` line the first time a file is linked to a post.
- **Nothing is ever deleted remotely:** not posts, media, terms or comments.

### How a file is matched to a post

1. `wordpress_id` in front matter, if present.
2. Otherwise, the post whose slug exactly matches. Drafts, pending, scheduled,
   private and published posts are all searched.
3. Exactly one match: use it, and record its ID. No match: create a post
   (`sync`/`publish` only). Several matches: stop and ask you to add
   `wordpress_id`.

After the first sync the ID is in front matter, so renaming the file or
changing its slug updates the same post rather than creating a duplicate.

### Where sync metadata lives (and why)

- `wordpress_id` goes in **front matter**. It is identity. It travels with the
  file through renames and `_drafts/` → `_posts/` moves, and it is written once
  as a single inserted line. The rest of the front matter is left byte-for-byte
  intact.
- The **baseline** goes in `.wordpress/posts/<id>.json`, which is committed and
  holds no secrets. That is: remote modification time, hashes of the remote
  title, content, excerpt and terms, and a hash of what was last sent. It
  changes on every sync. Keeping it out of front matter means your files don't
  get rewritten under Vim on each sync, and post diffs stay about the writing.
- `.wordpress/media.json` maps image files (by SHA-256) to media-library IDs.

Trade-off: the baseline is a second file to commit. If it is lost, nothing
breaks. The next `update` just treats the post as never synced, and asks for
`--force` if WordPress holds different content. Front matter alone would be
self-contained, but noisy. Front matter may still carry `wordpress_modified:
<modified_gmt>` as a manual baseline hint, and `wordpress_status` is accepted
but ignored (status is never taken from a file).

### Markdown conversion

Markdown is rendered to HTML with [markdown-it-py](https://github.com/executablebooks/markdown-it-py)
(CommonMark, plus tables, strikethrough and footnotes). Each top-level element
is then wrapped as a Gutenberg block:

| Markdown | WordPress block |
|---|---|
| paragraph | `core/paragraph` |
| `#`…`######` heading | `core/heading` |
| `<!--more-->` (alone or at a paragraph's end) | `core/more`, so archives and emails show the teaser |
| image alone in a paragraph | `<figure class="wp-block-image">` in `core/html`; a Markdown title (`![alt](x.png "Caption")`) becomes the caption |
| lists, blockquotes, code, tables, footnotes, rules, raw HTML | `core/html` |

**Why this design:** paragraphs and headings are native, so the post reads
normally in the editor. Everything else is a Custom HTML block. Its markup never
fails the block editor's validation, and it renders exactly what was generated.
Native list/image/code blocks would be nicer to edit in wp-admin. But their
saved markup changes between WordPress versions, and Markdown is the place to
edit. The output is deterministic: an unchanged file produces byte-identical
content, so `sync` reports "Already up to date" and sends nothing.

Other behaviour:

- Front matter is never sent in the body. Jekyll-only keys (`layout`, `author`,
  `permalink`…) are ignored.
- Typography is applied as kramdown did under Jekyll: curly quotes, `---` → —,
  `--` → –, `...` → …, in the body and the title. Code is left alone.
  wp-post does this itself because this site does **not** run WordPress's
  `wptexturize` on posts (checked 2026-11-10).
- Raw HTML (e.g. the `<figure>` pair in the typography post) passes through
  unchanged, apart from local `src` paths being rewritten to uploaded media.
- Liquid (`{% %}`, `{{ }}`) is not rendered. No post uses it; `validate` warns
  if one does.
- A body containing `<!-- wp:` comments is rejected, because it would corrupt
  the block structure.

### Commands

| Command | What it does | Writes? |
|---|---|---|
| `doctor [--setup]` | Checks config, API, auth and capabilities. `--setup` stores credentials first. | No (setup writes `.wp-post.env` locally) |
| `validate FILE… / --all` | Offline checks: front matter, images, metadata, term limit, duplicate slugs/IDs | No; no network |
| `status FILE [--diff]` | How the file relates to WordPress, conflicts, next step | No |
| `list` | Every WordPress post with its local file | No |
| `sync FILE` | New post → **draft**. Existing draft/pending → updated, same status. Scheduled/published/private → **refused** | Yes |
| `publish FILE` | New or draft → **publish** (or **future** if dated ahead). Summary + typed confirmation. Already live or scheduled → refused | Yes |
| `update FILE` | Existing post of any status → updated **in place**, status unchanged. Not found → refused | Yes |

Flags for `sync`, `publish` and `update`:

- `--dry-run` / `-n`: plan only. It sends GET requests only (the client refuses
  writes outright) and changes no files.
- `--force`: proceed past a conflict, or past a live-post URL change.
- `--yes` (`publish` only): skip the confirmation prompt. Never implied. Without
  a terminal and without `--yes`, `publish` refuses.
- `--allow-many-terms` (`publish`, `update`): permit more than 15 tags+categories.

Exit statuses: `0` ok · `2` usage · `3` conflict · `4` config/auth ·
`5` local validation · `6` API/network · `7` refused by a safety rule ·
`8` declined at the prompt · `1` unexpected.

## Authentication

wp-post uses the **standard WordPress REST API on the site itself**
(`https://dogdogfish.com/wp-json/wp/v2/`) with an **Application Password**
over HTTPS Basic auth.

How that was chosen (checked 2026-11-10, read-only):

- `https://dogdogfish.com/wp-json/` lists the `wp/v2` namespace and advertises
  `"authentication": {"application-passwords": …}` with the authorization
  endpoint `/wp-admin/authorize-application.php`.
- `https://public-api.wordpress.com/wp/v2/sites/258560523/` also answers. It
  would need a WordPress.com OAuth2 app and token, which is more setup for no
  benefit while Application Passwords work.

An Application Password is per-application and revocable, and it cannot be used
to log in to wp-admin. It is not your WordPress.com password.

### Create the Application Password

1. Log in to the site, then open
   **https://dogdogfish.com/wp-admin/authorize-application.php?app_name=wp-post**.
   Alternatively: wp-admin → **Users → Profile** → *Application Passwords* →
   name it `wp-post` → **Add New Application Password**.
2. Approve. WordPress shows the password **once**, as `xxxx xxxx xxxx xxxx xxxx xxxx`.
3. In the repository:

   ```sh
   ./bin/wp-post doctor --setup
   ```

   It asks for the username (your WordPress username, shown on the Profile page),
   then stores the password in one of two places:
   - **macOS Keychain** (recommended): the Keychain's own prompt reads it.
     Service `wp-post`, account = your username.
   - **`.wp-post.env`**: a hidden prompt, file mode 600, git-ignored.

   It then runs the checks.

Credentials are read from, in order: environment variables → `.wp-post.env` →
Keychain (password only). There is no `--password` flag, because argv is visible
in shell history and `ps`. wp-post never prints the password; all output passes
through redaction, which is covered by tests.

| Variable | Meaning |
|---|---|
| `WP_SITE_URL` | `https://dogdogfish.com`. Defaults to `url` in `_config.yml`; https only |
| `WP_SITE_ID` | `258560523`. Optional; doctor checks it matches the URL |
| `WP_USERNAME` | WordPress username owning the Application Password |
| `WP_APPLICATION_PASSWORD` | The Application Password |

`doctor` checks the following, without creating, editing or publishing anything:

- the config sources;
- the env file's permissions, and that it is git-ignored;
- that the API is reachable and Application Passwords are advertised;
- that the site ID matches;
- authentication (`/users/me`);
- the capabilities `edit_posts`, `publish_posts`, `edit_published_posts`,
  `upload_files` and `manage_categories`;
- edit-context read access to drafts, tags and media.

**If Application Passwords turn out not to work on this Atomic site:**
doctor reports `401 … application_passwords_disabled` or `incorrect_password`
with a fresh password. The fallback is WordPress.com OAuth2 against
`https://public-api.wordpress.com/wp/v2/sites/258560523/`:
1. Register an app at developer.wordpress.com/apps.
2. Obtain a token with the `global` or site-scoped grant.
3. Point the client at that base URL with an `Authorization: Bearer` header.

The routes are identical, so the change is confined to `tools/wp_post/client.py`
(base URL and header) and `config.py` (one variable). It is not implemented,
because the site advertises Application Passwords and they are the documented
preference.

## 3. Installation

Requires [uv](https://docs.astral.sh/uv/) (`brew install uv`). Python and the
dependencies in `uv.lock` are installed on first run.

```sh
uv sync                       # optional; ./bin/wp-post does this on demand
./bin/wp-post doctor --setup
uv run pytest -q              # tests: fully mocked, no network
uv run ruff check . && uv run ruff format --check .
```

Dependencies: `markdown-it-py`, `mdit-py-plugins`, `PyYAML`, `requests`
(dev: `pytest`, `ruff`). The code is in `tools/wp_post/`. Jekyll already
excludes `tools/`, and `_config.yml` excludes the other new files.

## 4. Writing a draft in Vim

```sh
vim _drafts/my-post.md
```

```markdown
---
layout: post
title: "My Post Title"
tags: [python, data-science]
---

The teaser paragraph.<!--more-->

The rest, in ordinary Markdown.
```

Supported front matter:

| Key | Notes |
|---|---|
| `title` | Required. Quote it if YAML could misread it (`"No"`, `"Yes"`, `"1984"`) |
| `date` | `2026-11-12`, or `2026-11-12 09:30:00 +0000`. Overrides the filename date, as in Jekyll |
| `slug` | Defaults to the filename minus any date, slugified like Jekyll (`my_post` → `my-post`) |
| `tags`, `categories` | Lists. A plain string is split on spaces, as in Jekyll |
| `excerpt` | Sets the WordPress excerpt. Without it, `<!--more-->` drives teasers |
| `featured_image` | Local image path (see §15) |
| `comment_status` / `comments` | `open`/`closed`, or `true`/`false`. See §12 |
| `newsletter` | `false` publishes without emailing subscribers. See §11 |
| `published: false` | Jekyll's flag. `publish` refuses the file |
| `wordpress_id` | Written by wp-post. Edit by hand only to link a file deliberately |
| `wordpress_modified` | Optional manual baseline hint. `wordpress_status` is ignored |

Tip: leave `date:` out of drafts and let the `_posts/YYYY-MM-DD-…` filename
supply it when you move the file. A stale `date:` in a draft will **backdate**
the published post. `publish` shows the date and warns when it is in the past.

The first `sync` inserts `wordpress_id: N` into the file. If it is open in Vim,
reload with `:e` (or `:set autoread`) before your next save.

## 5. Synchronizing a WordPress draft

```sh
./bin/wp-post sync _drafts/my-post.md --dry-run   # what would happen
./bin/wp-post sync _drafts/my-post.md
```

The output shows what changed (or "Already up to date") and the **Edit** and
**Preview** URLs. Repeat as often as you like: only changed fields are sent.

## 6. Previewing

Open the printed `Preview:` URL while logged in to WordPress. It looks like
`https://dogdogfish.com/?p=123&preview=true`. You can also use the editor's
Preview button from the `Edit:` URL. `./bin/wp-post status FILE` prints both
again. For a local preview of the old Jekyll theme, `bundle exec jekyll serve
--drafts` still works.

## 7. Publishing deliberately

```sh
git mv _drafts/my-post.md _posts/2026-11-12-my-post.md
./bin/wp-post publish _posts/2026-11-12-my-post.md --dry-run
./bin/wp-post publish _posts/2026-11-12-my-post.md
```

`publish` prints a summary before doing anything:

```
About to PUBLISH. This makes the post public.
  Title:       My Post Title
  Slug:        my-post
  Date:        2026-11-12 (from filename)
  Tags:        python, data-science
  Categories:  (not set locally: existing or default category)
  Status:      draft → publish
  First publication: yes. When it goes live, WordPress will email it to subscribers
  (Jetpack Newsletter) and may auto-share it to connected social accounts. Add
  `newsletter: false` to skip the email.

Type "publish" to make this post public:
```

Anything other than `publish` aborts with exit status 8, and nothing changes.
`--yes` skips the prompt for scripted use. Use it knowingly. Once the post is
live, commit the file and `.wordpress/`.

## 8. Updating a published post safely

```sh
./bin/wp-post update _posts/2026-11-12-my-post.md --dry-run
./bin/wp-post update _posts/2026-11-12-my-post.md
```

- `update` sends one `POST /wp/v2/posts/<id>` containing only the changed
  fields, and never a status. The post keeps its ID, URL, comments, Likes and
  stats. Tests assert that no create request is made.
- Changing the **slug or date** of a live post changes its public URL, so
  `update` refuses unless you pass `--force`. WordPress redirects the old URL.
- `sync` and `publish` refuse live posts, so a slip of the finger cannot touch them.

### The 110 migrated posts

All existing posts were imported (published) by the migration, with slugs that
match their filenames, so wp-post finds each one by slug. None has a sync
baseline yet. The importer's markup also differs from what wp-post generates.
So the first `update` of a migrated post stops with a conflict that explains
this. Check it with `status FILE --diff`, then use `update FILE --force` once
you're happy. After that the post behaves normally. There is no need to touch
posts you are not changing. Updating a migrated post does not re-send it to
subscribers (see §11).

## 9. Scheduling

Give the post a future date, then `publish` it. wp-post sends status `future`,
and WordPress publishes it at that time.

```yaml
date: 2026-12-01 08:00:00 +0000   # explicit time and zone recommended
```

A date-only value means midnight in the site's timezone (currently UTC). To
change a scheduled post's content or date, use `update`; it stays scheduled.
To unschedule, switch it back to draft in wp-admin. Newsletter emails go out
when the post goes live, not when you schedule it.

## 10. Tags, categories and Reader

- Terms are matched to existing ones **case-insensitively**, by name or by slug
  (`Python` reuses `python`). Missing terms are created, and duplicates differing
  only in case are collapsed locally with a warning.
- **Front matter is canonical, and it replaces.** If `tags:` is present, the
  post's tags become exactly that list. Likewise `categories:`. If the key is
  absent, that taxonomy is not sent and WordPress keeps whatever it has. New
  posts get the default category.
- Tag or category changes made in wp-admin since the last sync count as a
  conflict, so terms are never removed unexpectedly.
- **Reader:** WordPress.com Reader leaves posts with **more than 15 tags +
  categories combined** out of its topic listings. `publish` and `update` of a
  public post refuse beyond 15 unless you pass `--allow-many-terms`. `sync` and
  `validate` warn. Posts are ordinary public posts with tags, so they are
  eligible for Reader topics.

**Note on the migration:** the imported posts currently have **no tags**, and 32
of them carry odd categories named `01`…`31` (apparently day-of-month from the
old URLs). The other 78 are *Uncategorized*. Your front matter tags reach
WordPress the first time each post is updated. The day-number categories need
tidying in wp-admin (Posts → Categories). wp-post never deletes terms.

## 11. Newsletter implications

The site emails new posts to subscribers by default (Jetpack Newsletter). That
email is triggered when a post **first becomes public**: `publish`, or a
scheduled post going live.

- `sync` never makes anything public, so it never emails.
- `update` never changes status, so editing a live post does not re-send it.
  wp-post never unpublishes and republishes, and never deletes and recreates.
- To publish a post **without** emailing it, add `newsletter: false` to its
  front matter. wp-post sets Jetpack's per-post "don't email" flag
  (`_jetpack_dont_email_post_to_subs`, the editor's newsletter-panel setting).
  On `publish` it saves that flag while the post is still a draft, reads it
  back, and only then changes the status in a separate request. If WordPress
  did not keep the flag, it refuses to publish. The summary says
  "will NOT be emailed". Social auto-sharing is a separate setting.
- Without the key, wp-post sends no newsletter meta and the site default
  (email) applies. `newsletter: true` explicitly clears the flag.
- The flag only matters at first publication. Changing it on a live post
  sends no email and recalls none.
- Migrated posts are already published. Nothing here will email them.
- Publicize/Jetpack Social may also share a newly published post to connected
  accounts. Check Tools → Marketing → Connections if that matters.

There are no subscribers yet, so the confirmation prompt is the guard rail for
when there are.

## 12. Comments

- New posts are created with `comment_status: open`, unless front matter says
  `comments: false` or `comment_status: closed`.
- When updating, comment status is sent only if the front matter sets it.
  Otherwise whatever WordPress has is kept, including changes made in wp-admin.
- wp-post never reads, modifies or deletes comments.

## 13. WordPress.com Likes

Likes are a site and template setting, not post content, so wp-post does not
manage them. **Configured 2026-11-10.** Three things have to be true:

1. The Jetpack **Likes** module is active.
2. wp-admin → **Settings → Sharing** → *WordPress.com Likes are* → **On for all
   posts**. The migration had left it on *Turned on per post*, and every post
   reported Likes off.
3. **On a block theme like this one, the legacy auto-inserted Like button does
   not render.** The Like block must be in the template. A
   `jetpack/like` block now sits directly after Post Content in all four post
   templates (`single` and the three `single-post-article-*` templates).
   Edit them under Appearance → Editor → Templates.

To check:

1. Open a published post in a private window. Below the content you should see
   **☆ Like** (and any likers' avatars). For a single post, the editor's
   sidebar *Likes and Shares* panel can hide it, so check that if one post
   lacks the button.
3. In Reader (wordpress.com/read), follow the site, or search for a post. The
   post's card and full view show the Like control, and liking it there raises
   the count on the site.

## 14. Subscriptions and the Subscribe block

- Newsletter settings: wp-admin → **Jetpack → Newsletter** (or Settings →
  Newsletter). "Email new posts to subscribers" is on.
- **Where the forms are (set 2026-11-10):** the same three places as the old
  Jekyll site:
  - the homepage hero (page *Home*);
  - the `/subscribe/` page;
  - the site-wide **footer** template part, which also puts it under every
    post.

  Each is a Jetpack **Subscribe** block (`jetpack/subscriptions`). The
  migration had turned the old Buttondown forms into Jetpack *contact forms*,
  which only sent the site owner a feedback message. Nobody had submitted one.
- To edit them: Pages → Home / Subscribe, and Appearance → Editor → Patterns →
  Template Parts → Footer. Pages keep revisions. The footer can be reset to the
  theme's version from the Site Editor (that would bring back the dead contact
  form).
- Check it in a private window: subscribe with a test address and confirm that
  it appears under **Jetpack → Subscribers**.
- **Buttondown subscribers.** The old Jekyll forms posted to Buttondown
  (`_includes/subscribe-form.html`). To move those subscribers over:
  1. buttondown.com → Subscribers → **Export** (CSV).
  2. wordpress.com/subscribers/dogdogfish.com → **Add subscribers** → upload the
     CSV.
  3. Afterwards, disable the Buttondown newsletter so nobody signs up there.

## 15. Images and featured images

- References resolve like Jekyll: `/assets/images/x.png` from the repository
  root, and `img/x.png` relative to the Markdown file. Paths escaping the
  repository are refused. External `https://` images are left untouched.
- Every local image is checked **before anything is sent**:
  - It must exist.
  - It must not contain GPS/EXIF data or a hidden Motion Photo trailer. This
    uses the same check as the pre-commit hook. Fix with
    `python3 tools/image_metadata.py strip FILE`.
- **Deduplication by content:**
  - An image whose SHA-256 is in `.wordpress/media.json` is reused, after
    confirming the media item still exists.
  - Otherwise the media library is searched for the same filename (including
    `-1` and `-scaled` variants) and compared byte for byte. That is how the
    images the migration already uploaded (media 4–27) are adopted rather than
    duplicated.
  - Only then is the image uploaded.
- An image changed locally gets a new hash, so it is uploaded as a new media
  item and the post points to it. The old item is kept, and listed under
  `previous` in the manifest. Remote media is never deleted.
- Only the **generated HTML** is rewritten. Your Markdown keeps its
  `/assets/images/...` paths.
- Alt text comes from `![alt](…)`, and line-wrapped alt text is joined. A
  Markdown title becomes a caption: `![alt](x.png "Caption")`. Images get the
  `wp-image-<id>` class, so WordPress adds `srcset` and lazy loading.
- `featured_image: /assets/images/x.jpg` uploads or reuses that image and sets
  it as the featured image. It must be a local file; URLs are rejected.

## 16. Conflicts

After every write, wp-post records the remote modification time and hashes of
the title, content, excerpt and terms. Before the next write it fetches the post
again:

- **Tracked fields unchanged:** proceeds. If only the timestamp moved (someone
  pressed Update without changing anything), it warns and continues.
- **Tracked fields changed:** stops with exit status **3**. Nothing is sent.
  It shows which fields changed, both timestamps, the edit URL (whose
  *Revisions* panel shows who changed what), and a diff of WordPress's version
  against yours.
- **No baseline** (e.g. migrated posts, or a lost manifest), and the content
  differs: also a conflict.

To resolve one, either:

- copy the wp-admin change into the Markdown by hand, then `update --force`; or
- decide the Markdown wins, and run `update --force`.

The overwritten version stays in WordPress revisions. There is no automatic
remote-to-local merge.

## 17. Credential rotation

1. Create a new Application Password (§2), named e.g. `wp-post-2027`.
2. `./bin/wp-post doctor --setup`, then paste the new one. The Keychain entry or
   `.wp-post.env` is replaced.
3. `./bin/wp-post doctor` and expect *All checks passed*.
4. Revoke the old password: **Users → Profile → Application Passwords** →
   **Revoke** next to the old name.

## 18. Troubleshooting and recovery

The usual sequence is `./bin/wp-post doctor`, then `./bin/wp-post status FILE`,
then the same command with `--dry-run`.

| Symptom | Cause / fix |
|---|---|
| `HTTP 401 incorrect_password` / `invalid_username` | Wrong username, or a login password instead of an Application Password. Re-run `doctor --setup` |
| `401 application_passwords_disabled` | Disabled by the host or a plugin. See the OAuth fallback in §2 |
| `… was redirected (HTTP 301)` | `WP_SITE_URL` isn't canonical (www vs apex, http). Use `https://dogdogfish.com` |
| `HTTP 403` | The account lacks a capability. doctor lists which |
| network error | Offline, VPN or DNS. Nothing was half-applied: post writes are a single request |
| exit 3 conflict | See §16 |
| `refusing to guess` (several posts share a slug) | Add `wordpress_id:` with the right ID (see `list`) |
| `already linked to <other file>` | Two files claim one post. Delete the stale copy, or give one a new `slug:` |
| `matched post N only by slug … distinct slug` | A new draft collides with an existing post's slug. E.g. `_drafts/psychological_discomfort.md` vs the live `psychological-discomfort`: add `slug: something-else` |
| `wordpress_id N does not exist` | The post was permanently deleted, or the ID is wrong. wp-post will not recreate it. Remove the line to start a new draft |
| `post N is in the trash` | Restore it in Posts → Trash |
| Vim: "file changed since editing started" | wp-post inserted `wordpress_id`. `:e` to reload |
| `.wordpress/posts/N.json` lost or corrupt | Delete it. The next `update` needs `--force` once if content differs |

**Recovery:**

- WordPress keeps **revisions** of every update: Edit → Revisions → Restore.
- wp-post never deletes posts, media, terms or comments. Partial runs leave at
  most a new tag or an uploaded image, both recorded and reused next time.
- Git holds every version of the Markdown and the manifest.

## 19. Revoking publishing access immediately

1. wp-admin → **Users → Profile → Application Passwords** → **Revoke** the
   `wp-post` entry, or **Revoke all application passwords**. Effective at once.
   Every wp-post request fails with 401 from then on.
2. Remove local copies:
   `security delete-generic-password -s wp-post -a <username>` (Keychain) and/or
   `rm .wp-post.env`.
3. If a password leaked, check **Posts** and **Media** for anything unexpected,
   and consider changing your WordPress.com password and reviewing connected
   applications at wordpress.com/me/security.

## Reference

- Tool source: `tools/wp_post/` (`publisher.py` holds the safety rules).
  Tests: `tests/`.
- CI: `.github/workflows/check.yml` runs lint, tests, `validate --all` and the
  image-metadata check. It has no secrets and never contacts WordPress.
- Migration history: [migration-from-github-pages.md](migration-from-github-pages.md).
