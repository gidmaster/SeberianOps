from fastapi import APIRouter, Request, HTTPException
from app.templates import templates
from app.services.posts import get_all_posts, get_post_by_slug, get_all_tags

router = APIRouter()

@router.get("/")
async def index(request: Request, tag: str | None = None):
    posts = get_all_posts(tag=tag)
    tags = get_all_tags()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "posts": posts, "tags": tags, "active_tag": tag}
    )

@router.get("/post/{slug}")
async def post_detail(request: Request, slug: str):
    post = get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return templates.TemplateResponse(
        "post.html",
        {"request": request, "post": post}
    )
