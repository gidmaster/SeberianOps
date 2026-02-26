from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.templates import templates
from app.services.pages import get_page
from app.services.posts import get_all_posts, get_post_by_slug, get_all_tags
from app.database.engine import get_db
from app.repositories.post_stat import PostStatRepository

router = APIRouter()

@router.get("/")
async def index(request: Request, tag: str | None = None):
    posts = get_all_posts(tag=tag)
    tags = get_all_tags()
    return templates.TemplateResponse(
        request,
        "index.html",
        {"request": request, "posts": posts, "tags": tags, "active_tag": tag}
    )

@router.get("/post/{slug}")
async def post_detail(
    request: Request,
    slug: str,
    db: AsyncSession = Depends(get_db)
):
    post = get_post_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    repo = PostStatRepository(db)
    stat = await repo.increment_view(slug)

    return templates.TemplateResponse(
        request,
        "post.html",
        {"request": request, "post": post, "view_count": stat.view_count}
    )

@router.get("/about")
async def about(request: Request):
    page = get_page("about")
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return templates.TemplateResponse(
        request,
        "page.html",
        {"request": request, "page": page}
    )

@router.get("/page/{slug}")
async def static_page(request: Request, slug: str):
    page = get_page(slug)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return templates.TemplateResponse(
        request,
        "page.html",
        {"request": request, "page": page}
    )
