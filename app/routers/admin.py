from fastapi import APIRouter, Header, HTTPException
from app.services.posts import invalidate_cache
from app.config import settings

router = APIRouter(prefix="/admin")

@router.post("/cache/invalidate")
async def cache_invalidate(x_admin_token: str = Header(...)):
    if x_admin_token != settings.admin_token:
        raise HTTPException(status_code=403, detail="Forbidden")
    invalidate_cache()
    return {"status": "ok", "message": "Cache invalidated"}
