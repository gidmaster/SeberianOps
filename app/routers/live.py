from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.templates import templates
from app.database.engine import get_db
from app.repositories.live_entry import LiveEntryRepository
from app.schemas.live_entry import LiveEntryView
from app.config import settings
import markdown2

router = APIRouter(prefix="/live")

PAGE_SIZE = 20

def render_body(text: str) -> str:
    return markdown2.markdown(text, extras={"fenced-code-blocks": {"cssclass": "highlight"}})

@router.get("/")
async def live_index(
    request: Request,
    page: int = 1,
    db: AsyncSession = Depends(get_db)
):
    repo = LiveEntryRepository(db)
    offset = (page - 1) * PAGE_SIZE
    entries = await repo.get_all(limit=PAGE_SIZE, offset=offset)
    total = await repo.count()
    total_pages = (total + PAGE_SIZE - 1) // PAGE_SIZE

    entry_views = [
        LiveEntryView.from_model(entry, render_body(entry.body))
        for entry in entries
    ]

    return templates.TemplateResponse(
        "live.html",
        {
            "request": request,
            "entries": entry_views,
            "page": page,
            "total_pages": total_pages,
            "total": total,            
        }
    )

@router.post("/entry")
async def create_entry(
    request: Request,
    body: str = Form(...),
    pinned: bool = Form(False),
    x_admin_token: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    
    repo = LiveEntryRepository(db)
    await repo.create(body=body, pinned=pinned)
    return RedirectResponse(url="/live", status_code=303)

@router.post("/entry/{entry_id}/delete")
async def delete_entry(
    entry_id: int,
    x_admin_token: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    repo = LiveEntryRepository(db)
    deleted = await repo.delete(entry_id=entry_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse(url="/live", status_code=303)

@router.post("/entry/{entry_id}/pin")
async def pin_entry(
    entry_id: int,
    x_admin_token: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")

    repo = LiveEntryRepository(db)
    entry = await repo.toggle_pin(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Entry not found")
    return RedirectResponse(url="/live", status_code=303)