from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.templates import templates
from app.database.engine import get_db
from app.repositories.post_stat import PostStatRepository
from app.repositories.live_entry import LiveEntryRepository
from app.schemas.live_entry import LiveEntryView
from app.auth import (
    create_session, verify_session, get_session,
    require_admin, SESSION_COOKIE, SESSION_MAX_AGE
)
from app.config import settings
from app.routers.live import render_body
import markdown2

router = APIRouter(prefix="/admin")

# ── Auth ─────────────────────────────────────────────────

@router.get("/login")
async def login_page(request: Request):
    token = get_session(request)
    if token and verify_session(token):
        return RedirectResponse(url="/admin", status_code=303)
    return templates.TemplateResponse(
        request,
        "admin/login.html",
        {"request": request, "error": None}
    )

@router.post("/login")
async def login(
    request: Request,
    password: str = Form(...)
):
    if password != settings.admin_token:
        return templates.TemplateResponse(
            request,
            "admin/login.html",
            {"request": request, "error": "Invalid password"},
            status_code=401
        )
    
    response = RedirectResponse(url="/admin", status_code=303)
    response.set_cookie(
        key=SESSION_COOKIE,
        value=create_session(),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        samesite="lax"
    )
    return response

@router.get("/logout")
async def logout():
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response

# ── Dashboard ────────────────────────────────────────────

@router.get("/")
async def dashboard(
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    post_repo = PostStatRepository(db)
    live_repo = LiveEntryRepository(db)

    post_stats = await post_repo.get_all_stats()
    recent_entries = await live_repo.get_all(limit=5)
    total_entries = await live_repo.count()

    entry_views = [
        LiveEntryView.from_model(e, render_body(e.body))
        for e in recent_entries
    ]

    return templates.TemplateResponse(
        request,
        "admin/dashboard.html",
        {
            "request": request,
            "post_stats": post_stats,
            "recent_entries": entry_views,
            "total_entries": total_entries,
        }
    )

# ── Live entries management ──────────────────────────────

@router.get("/live")
async def live_manage(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    repo = LiveEntryRepository(db)
    PAGE_SIZE = 20
    offset = (page - 1) * PAGE_SIZE
    entries = await repo.get_all(limit=PAGE_SIZE, offset=offset)
    total = await repo.count()
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    entry_views = [
        LiveEntryView.from_model(e, render_body(e.body))
        for e in entries
    ]

    return templates.TemplateResponse(
        request,
        "admin/live.html",
        {
            "request": request,
            "entries": entry_views,
            "page": page,
            "total_pages": total_pages,
            "total": total,
        }
    )

@router.post("/live/entry")
async def create_entry(
    request: Request,
    body: str = Form(...),
    pinned: bool = Form(False),
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    repo = LiveEntryRepository(db)
    await repo.create(body=body, pinned=pinned)
    return RedirectResponse(url="/admin/live", status_code=303)

@router.post("/live/entry/{entry_id}/delete")
async def delete_entry(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    repo = LiveEntryRepository(db)
    deleted = await repo.delete(entry_id)
    if not deleted:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse(url="/admin/live", status_code=303)

@router.post("/live/entry/{entry_id}/pin")
async def pin_entry(
    entry_id: int,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_admin)
):
    repo = LiveEntryRepository(db)
    await repo.toggle_pin(entry_id)
    return RedirectResponse(url="/admin/live", status_code=303)


@router.post("/cache/invalidate")
async def cache_invalidate(
    request: Request,
    _: None = Depends(require_admin)
):
    from app.services.posts import invalidate_cache
    invalidate_cache()
    return {"status": "ok", "message": "Cache invalidated"}
