# .wordpress/: sync manifest (committed, no secrets)

Written by `./bin/wp-post`. Commit it along with your posts.

- `posts/<wordpress_id>.json`: the baseline from the last successful sync of
  each post: hashes of the remote title, content, excerpt and terms, the remote
  modification time, and the source file. It is used to detect edits made in
  wp-admin (conflicts) and to skip no-op updates.
- `media.json`: local image path → SHA-256, WordPress media ID and URL. It is
  used so the same bytes are never uploaded twice.

It is safe to delete a `posts/N.json`. The next `update` will then treat the post
as never synced, and will ask for `--force` if WordPress has different content.
Deleting `media.json` is also safe: images are re-matched against the media
library byte for byte, not re-uploaded.
