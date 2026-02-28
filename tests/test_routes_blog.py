import pytest
from httpx import AsyncClient
import os
import tempfile
import shutil
from app.services.posts import invalidate_cache

# ── Helpers ──────────────────────────────────────────────

def create_test_post(directory: str, filename: str, content: str):
    """Helper to create a markdown post file for testing."""
    filepath = os.path.join(directory, filename)
    with open(filepath, "w") as f:
        f.write(content)
    return filepath

SAMPLE_POST = """---
title: Test Post
date: 01.01.2026
slug: test-post
summary: A test post summary
tags:
  - devops
  - python
---

## Hello

This is a test post with some `inline code`.
```bash
echo "hello world"
```
"""

SAMPLE_POST_2 = """---
title: Another Post
date: 02.01.2026
slug: another-post
summary: Another summary
tags:
  - kubernetes
---

## Another post content
"""

# ── Fixtures ─────────────────────────────────────────────

@pytest.fixture(autouse=True)
def test_posts_dir(monkeypatch, tmp_path):
    """
    Replace real posts directory with a temp directory.
    monkeypatch replaces POSTS_DIR only for the duration of the test.
    """
    posts_dir = tmp_path / "posts"
    posts_dir.mkdir()

    monkeypatch.setattr("app.services.posts.POSTS_DIR", str(posts_dir))
    invalidate_cache()  # clear cache so tests see temp dir
    yield str(posts_dir)
    invalidate_cache()  # clean up after

# ── Index route tests ─────────────────────────────────────

async def test_index_empty(client: AsyncClient, test_posts_dir):
    """Index page loads with no posts."""
    response = await client.get("/")
    assert response.status_code == 200
    assert "MyBlog" in response.text or "SiberianOps" in response.text

async def test_index_shows_posts(client: AsyncClient, test_posts_dir):
    """Index page lists existing posts."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    response = await client.get("/")
    assert response.status_code == 200
    assert "Test Post" in response.text
    assert "A test post summary" in response.text

async def test_index_tag_filter(client: AsyncClient, test_posts_dir):
    """Tag filter shows only matching posts."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    create_test_post(test_posts_dir, "another-post.md", SAMPLE_POST_2)
    invalidate_cache()

    response = await client.get("/?tag=kubernetes")
    assert response.status_code == 200
    assert "Another Post" in response.text
    assert "Test Post" not in response.text

async def test_index_tag_filter_no_results(client: AsyncClient, test_posts_dir):
    """Tag filter with no matches shows empty page without error."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    response = await client.get("/?tag=nonexistent")
    assert response.status_code == 200

# ── Post detail tests ─────────────────────────────────────

async def test_post_detail(client: AsyncClient, test_posts_dir):
    """Post detail page renders correctly."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    response = await client.get("/post/test-post")
    assert response.status_code == 200
    assert "Test Post" in response.text
    assert "Hello" in response.text

async def test_post_detail_increments_views(client: AsyncClient, test_posts_dir):
    """Visiting a post increments view count."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    await client.get("/post/test-post")
    await client.get("/post/test-post")
    response = await client.get("/post/test-post")

    assert response.status_code == 200
    assert "3" in response.text  # view count shown on page

async def test_post_detail_not_found(client: AsyncClient, test_posts_dir):
    """Non-existent post returns 404."""
    response = await client.get("/post/does-not-exist")
    assert response.status_code == 404

async def test_post_renders_markdown(client: AsyncClient, test_posts_dir):
    """Markdown content is rendered to HTML."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    response = await client.get("/post/test-post")
    assert response.status_code == 200
    assert "<code>" in response.text  # inline code rendered
    assert "<h2" in response.text    # heading rendered

# ── RSS feed tests ────────────────────────────────────────

async def test_rss_feed(client: AsyncClient, test_posts_dir):
    """RSS feed returns valid XML with posts."""
    create_test_post(test_posts_dir, "test-post.md", SAMPLE_POST)
    invalidate_cache()

    response = await client.get("/feed.xml")
    assert response.status_code == 200
    assert "application/rss+xml" in response.headers["content-type"]
    assert "Test Post" in response.text
    assert "<rss" in response.text

async def test_rss_feed_empty(client: AsyncClient, test_posts_dir):
    """RSS feed works with no posts."""
    response = await client.get("/feed.xml")
    assert response.status_code == 200
    assert "<rss" in response.text

# ── Error page tests ──────────────────────────────────────

async def test_404_returns_html(client: AsyncClient):
    """404 returns HTML error page, not JSON."""
    response = await client.get("/this-does-not-exist")
    assert response.status_code == 404
    assert "text/html" in response.headers["content-type"]
    assert "404" in response.text

async def test_about_page(client: AsyncClient, tmp_path, monkeypatch):
    """About page renders correctly."""
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()

    about_content = """---
title: About
---

## whoami

Test about content.
"""
    (pages_dir / "about.md").write_text(about_content)
    monkeypatch.setattr("app.services.pages.PAGES_DIR", str(pages_dir))

    response = await client.get("/about")
    assert response.status_code == 200
    assert "About" in response.text
    assert "whoami" in response.text
