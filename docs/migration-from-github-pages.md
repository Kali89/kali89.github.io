# Migration note: GitHub Pages → WordPress.com

## Before (until November 2026)

- `Kali89/kali89.github.io` was built by Jekyll and deployed to **GitHub
  Pages** by `.github/workflows/jekyll.yml` on every push to `main`
  (`build_type: workflow`).
- The custom domain `dogdogfish.com` was claimed through a `CNAME` file in the
  repository root, and through the repository's *Settings → Pages → Custom
  domain*.
- Permalinks were `/blog/:year/:month/:day/:title/`. Images were served from
  `/assets/images/`. The subscribe form posted to Buttondown.

## After

- `dogdogfish.com` is served by **WordPress.com (Atomic)**, blog ID 258560523.
  Permalinks are `/:year/:month/:day/:slug/`. Old `/blog/...` URLs answer with
  a 301 to the new ones (checked 2026-11-10).
- This repository stays the **canonical source** for post content. Posts reach
  WordPress only via `./bin/wp-post` (see
  [wordpress-publishing.md](wordpress-publishing.md)).
- The Jekyll layouts, Sass and assets stay for local previews
  (`bundle exec jekyll serve`) and as history. They no longer deploy anywhere.

## What changed in the repository

| Change | Why |
|---|---|
| Deleted `.github/workflows/jekyll.yml` (it remains in git history) | It rebuilt and deployed GitHub Pages on every push |
| Added `.github/workflows/check.yml` | Lint, tests and offline validation only. It never deploys and never contacts WordPress |
| Deleted `CNAME` (content was `dogdogfish.com`; it remains in git history) | So no future Pages build can claim the domain |
| `_config.yml` excludes the publisher's files | Keeps local Jekyll previews clean |

## Manual steps on GitHub (not done automatically)

Deleting the workflow stops new deployments. However, as of 2026-11-10 the
repository settings still say Pages is **built** with **custom domain
`dogdogfish.com`**, so GitHub still serves the last deployment and holds the
domain setting. To release it:

1. Repository → **Settings → Pages**: remove the custom domain, then
   **Unpublish site**. Or, with the GitHub CLI:

   ```sh
   gh api -X DELETE repos/Kali89/kali89.github.io/pages
   ```

2. Optional but recommended: in your account's **Settings → Pages → Verified
   domains**, verify `dogdogfish.com`. Then no other GitHub user can ever
   claim it, even if DNS is pointed back at GitHub by mistake.
3. Check: `gh api repos/Kali89/kali89.github.io/pages` should return 404, and
   `https://dogdogfish.com` should still be WordPress.

## What the import left behind (as observed 2026-11-10)

- All 110 posts are published, with slugs matching the filenames. Their dates
  follow the front matter, which in five cases differs from the filename;
  `validate` lists them.
- All 23 referenced images were uploaded (media IDs 4–27). wp-post adopts them
  by byte comparison instead of re-uploading.
- **No tags** were imported. **32 posts** got categories named `01`–`31`; the
  rest are *Uncategorized*. See the Tags section of the publishing guide.
