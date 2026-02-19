from fastapi import APIRouter, Request, HTTPException
from app.templates import templates
from app.services.posts import get_all_posts, get_post_by_slug

router = APIRouter()

@router.get("/")
async def index(request: Request):
    posts = get_all_posts()
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "posts": posts}
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
