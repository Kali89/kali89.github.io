# My Jekyll Blog

A clean, minimal blog built with Jekyll and hosted on GitHub Pages at **dogdogfish.com**.

## Quick Start (Deploy to GitHub Pages)

### 1. Create a GitHub Repository

Go to [github.com/new](https://github.com/new) and create a new repository.

Name it anything you like (e.g., `blog` or `dogdogfish.com`). Since you're using a custom domain, the repository name doesn't affect your URL.

### 2. Push This Code

```bash
cd matt-blog
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/yourusername/blog.git
git push -u origin main
```

### 3. Enable GitHub Pages

1. Go to your repository on GitHub
2. Click **Settings** → **Pages** (in the left sidebar)
3. Under "Source", select **GitHub Actions**
4. Wait a minute or two for the first build

### 4. Verify Your Custom Domain (Recommended)

For security, verify your domain with GitHub:

1. Go to your GitHub account **Settings** (click your profile photo → Settings)
2. Click **Pages** in the left sidebar
3. Click **Add a domain** and enter `dogdogfish.com`
4. Follow the instructions to add a TXT record to your DNS

### 5. Configure Your Custom Domain

In your repository's **Settings → Pages**:

1. Under "Custom domain", enter `dogdogfish.com`
2. Click **Save**
3. Once DNS propagates, tick **Enforce HTTPS**

Your site will be live at **https://dogdogfish.com** 🎉

## Writing New Posts

### Create a Post

Add a new file to the `_posts` folder with this naming format:

```
_posts/YYYY-MM-DD-title-of-your-post.md
```

For example: `_posts/2026-01-10-my-thoughts-on-python.md`

### Post Format

Every post needs "front matter" at the top:

```markdown
---
layout: post
title: "My Post Title"
date: 2026-01-10
tags: [python, data-science]
---

Your content here in Markdown...

## Subheading

More content...

```python
# Code blocks work too
print("Hello, world!")
```
```

### Working with Drafts

Put work-in-progress posts in `_drafts/` (no date in filename):

```
_drafts/my-unfinished-post.md
```

Drafts won't be published until you move them to `_posts/` with a date.

## Local Development (Optional)

If you want to preview your site locally before publishing:

### Prerequisites

- Ruby (2.7 or higher)
- Bundler (`gem install bundler`)

### Setup

```bash
bundle install
```

### Run Locally

```bash
bundle exec jekyll serve
```

Then visit `http://localhost:4000` in your browser.

## Customisation

### Site Settings

Edit `_config.yml` to change:

- `title` - Your blog's name
- `description` - Site description (for SEO)
- `author` - Your name
- `url` - Your site's URL (once deployed)

### Styling

The site uses SCSS for styling. Key files:

- `_sass/_variables.scss` - Colours, fonts, spacing
- `_sass/_base.scss` - Basic element styles
- `_sass/_layout.scss` - Header, footer, content layout
- `_sass/_components.scss` - Post lists, tags, etc.

### Adding Pages

Create a new `.md` file in the root directory:

```markdown
---
layout: page
title: "My New Page"
permalink: /my-page/
---

Page content here...
```

Then add it to the navigation in `_layouts/default.html`.

## Useful Markdown Tips

```markdown
**Bold text**
*Italic text*
[Link text](https://example.com)
![Image alt text](/assets/images/photo.jpg)

> Blockquote

- Bullet list
- Another item

1. Numbered list
2. Second item
```

## File Structure

```
matt-blog/
├── _config.yml          # Site configuration
├── _layouts/            # Page templates
│   ├── default.html     # Main wrapper
│   ├── page.html        # Static pages
│   └── post.html        # Blog posts
├── _posts/              # Your blog posts
│   └── 2026-01-05-welcome.md
├── _drafts/             # Unpublished drafts
├── _sass/               # Stylesheets
├── assets/
│   ├── css/
│   └── images/          # Your images
├── about.md             # About page
├── blog.html            # Blog index
└── index.html           # Homepage
```

## Need Help?

- [Jekyll Documentation](https://jekyllrb.com/docs/)
- [GitHub Pages Documentation](https://docs.github.com/en/pages)
- [Markdown Guide](https://www.markdownguide.org/)
