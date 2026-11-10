# DogDogFish

The source for **[dogdogfish.com](https://dogdogfish.com)**.

- **This repository is canonical.** Posts are written in Markdown, in `_drafts/`
  and `_posts/`, and versioned here.
- **WordPress.com is the publisher.** It handles rendering, comments, Likes,
  Reader, subscriptions, newsletter emails and stats.
- Posts reach WordPress only through `./bin/wp-post`, and **nothing goes live
  without an explicit `publish`**. Committing and pushing never publish.

The site used to be built by Jekyll and served from GitHub Pages; see
[docs/migration-from-github-pages.md](docs/migration-from-github-pages.md).

## Daily workflow

```sh
vim _drafts/my-post.md
./bin/wp-post sync _drafts/my-post.md            # WordPress draft + preview URL

git mv _drafts/my-post.md _posts/2026-11-12-my-post.md
./bin/wp-post publish _posts/2026-11-12-my-post.md    # summary, then type "publish"

./bin/wp-post update _posts/2026-11-12-my-post.md     # later edits to the live post
git add -A && git commit -m "My post"            # include .wordpress/
```

| Command | |
|---|---|
| `./bin/wp-post doctor [--setup]` | Check (or set up) credentials and permissions. Read-only |
| `./bin/wp-post validate --all` | Offline checks of every post. No credentials needed |
| `./bin/wp-post status FILE [--diff]` | How a file relates to its WordPress post |
| `./bin/wp-post list` | WordPress posts ↔ local files |
| `./bin/wp-post sync FILE` | Create/update a **draft**. Never touches live posts |
| `./bin/wp-post publish FILE [--yes]` | First publication, with confirmation |
| `./bin/wp-post update FILE` | Update an existing post in place, keeping its status |

`sync`, `publish` and `update` take `--dry-run` (no writes) and `--force`
(deliberately override a detected conflict).

**Full guide:** [docs/wordpress-publishing.md](docs/wordpress-publishing.md).
It covers setup, Application Passwords, conflicts, images, scheduling, Reader,
the newsletter, comments, Likes, credential rotation and troubleshooting.

## First-time setup

```sh
brew install uv                    # if needed
./bin/wp-post doctor --setup       # stores an Application Password (Keychain or .wp-post.env)
```

See [Authentication](docs/wordpress-publishing.md#authentication) for creating
the Application Password. Never commit credentials: `.wp-post.env` is
git-ignored, and `wp-post.env.example` lists the variable names.

## Post format

Existing Jekyll front matter works unchanged:

```markdown
---
layout: post
title: "My Post Title"
date: 2026-11-12
tags: [python, data-science]
---

Teaser.<!--more-->

Markdown content here.
```

Also supported: `slug`, `categories`, `excerpt`, `featured_image`,
`comments`/`comment_status`, and `wordpress_id` (written by the tool).
The date and slug come from the filename when front matter doesn't set them.

## Repository layout

```
_posts/, _drafts/      Markdown posts (canonical)
assets/images/         Images; uploaded to the media library on sync
.wordpress/            Committed sync manifest: post baselines, media IDs. No secrets
bin/wp-post            The publisher CLI (code in tools/wp_post/, tests in tests/)
tools/image_metadata.py  GPS/EXIF check, used by the pre-commit hook and by wp-post
docs/                  Publishing guide and migration note
_layouts/, _sass/, …   Jekyll theme: local preview only
```

## Development

```sh
uv run pytest -q                                   # WordPress API fully mocked
uv run ruff check . && uv run ruff format --check .
git config core.hooksPath .githooks                # image-metadata pre-commit hook
```

CI (`.github/workflows/check.yml`) runs the same checks plus
`wp-post validate --all`. It has no WordPress credentials and never contacts
WordPress.

## Local Jekyll preview (optional)

The Jekyll theme still builds locally for previewing Markdown:

```sh
bundle install
bundle exec jekyll serve --drafts    # http://localhost:4000
```

Production rendering is WordPress's theme, so this is an approximation.
