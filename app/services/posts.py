import os
import yaml
import markdown2
from dataclasses import dataclass, field
from datetime import date

POSTS_DIR = "content/posts"

@dataclass
class Post:
    title: str
    date: date
    slug: str
    summary: str
    content_html: str
    tags: list[str] = field(default_factory=list)

def parse_post(filepath: str) -> Post:
    with open(filepath, "r", encoding="utf-8") as f:
        raw = f.read()

    # Split frontmatter and content
    _, frontmatter, body = raw.split("---", 2)

    meta = yaml.safe_load(frontmatter)
    content_html = markdown2.markdown(body)

    return Post(
        title=meta["title"],
        date=meta["date"],
        slug=meta["slug"],
        summary=meta.get("summary", ""),
        tags=meta.get("tags", []),
        content_html=content_html
    )

def get_all_posts(tag: str | None = None) -> list[Post]:
    posts = []
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            filepath = os.path.join(POSTS_DIR, filename)
            posts.append(parse_post(filepath))

    if tag:
        posts = [p for p in posts if tag in p.tags]

    return sorted(posts, key=lambda p: p.date, reverse=True)

def get_post_by_slug(slug: str) -> Post | None:
    for post in get_all_posts():
        if post.slug == slug:
            return post
    return None

def get_all_tags() -> list[str]:
    tags = set()
    for post in get_all_posts():
        tags.update(post.tags)
    return sorted(tags)
