import os
import re
import time
import yaml
import markdown2
from pygments.formatters import HtmlFormatter
from dataclasses import dataclass, field
from datetime import date, datetime
from app.config import settings

POSTS_DIR = "content/posts"

@dataclass
class Post:
    title: str
    date: date
    slug: str
    summary: str
    content_html: str
    tags: list[str] = field(default_factory=list)

_cache: list[Post] = []
_cache_ts: float = 0.0
_CACHE_TTL = settings.cache_ttl

def _rewrite_image_paths(html: str) -> str:
    """
    Rewrites relative image src to absolute /images/ paths.
    <img src="face.jpg"> → <img src="/images/face.jpg">
    <img src="./face.jpg"> → <img src="/images/face.jpg">
    Leaves absolute paths (/images/..., http://...) untouched.
    """
    def replace(match):
        src = match.group(1)
        if src.startswith(("http://", "https://", "/", "data:")):
            return match.group(0)  # already absolute, leave it
        src = src.lstrip("./")
        src = os.path.basename(src)
        return f'src="/images/{src}"'

    return re.sub(r'src="([^"]*)"', replace, html)

def _is_cache_valid() -> bool:
    return bool(_cache) and (time.time() - _cache_ts) < _CACHE_TTL

def invalidate_cache() -> None:
    global _cache, _cache_ts
    _cache = []
    _cache_ts = 0.0

def _parse_date(value) -> date:
    if isinstance(value, date):
        return value
    value = str(value)
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value}")

def _parse_post(filepath: str) -> Post:
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split frontmatter and content
    _, frontmatter, body = raw.split("---", 2)

    meta = yaml.safe_load(frontmatter)
    content_html = markdown2.markdown(
        body,
        extras={
            "fenced-code-blocks": {"cssclass": "highlight"},
            "code-friendly": None,
            "tables": None,
            "strike": None,
            "header-ids": None,
        }
    )
    content_html = _rewrite_image_paths(content_html)

    return Post(
        title=meta["title"],
        date=_parse_date(meta["date"]),
        slug=meta["slug"],
        summary=meta.get("summary", ""),
        tags=meta.get("tags", []),
        content_html=content_html
    )

def _load_all_posts() -> list[Post]:
    posts = []
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            filepath = os.path.join(POSTS_DIR, filename)
            posts.append(_parse_post(filepath))
    return sorted(posts, key=lambda p: p.date, reverse=True)

def get_all_posts(tag: str | None = None) -> list[Post]:
    global _cache, _cache_ts

    if not _is_cache_valid():
        _cache = _load_all_posts()
        _cache_ts = time.time()

    if tag:
        return [p for p in _cache if tag in p.tags]
    return _cache

def get_post_by_slug(slug: str) -> Post | None:
    return next((p for p in get_all_posts() if p.slug == slug), None)

def get_all_tags() -> list[str]:
    return sorted(set(tag for post in get_all_posts() for tag in post.tags))
