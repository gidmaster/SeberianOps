import os
import yaml
import markdown2
from dataclasses import dataclass
from datetime import date

POSTS_DIR = "content/posts"

@dataclass
class Post:
    title: str
    date: date
    slug: str
    summary: str
    content_html: str

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
        content_html=content_html
    )

def get_all_posts() -> list[Post]:
    posts = []
    for filename in os.listdir(POSTS_DIR):
        if filename.endswith(".md"):
            filepath = os.path.join(POSTS_DIR, filename)
            posts.append(parse_post(filepath))
    return sorted(posts, key=lambda p: p.date, reverse=True)

def get_post_by_slug(slug: str) -> Post | None:
    for post in get_all_posts():
        if post.slug == slug:
            return post
    return None
