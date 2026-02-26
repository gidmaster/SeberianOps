from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from contextlib import asynccontextmanager
from app.config import settings
from app.routers import blog, feed, live
from app.routers import admin_panel
from app.errors import http_exception_handler, server_error_handler
from app.database.engine import engine
from app.database.base import Base
from app.database.models import post_stat, live_entry  # noqa: F401

@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    await engine.dispose()

app = FastAPI(title=settings.app_title, lifespan=lifespan)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, server_error_handler)

app.include_router(blog.router)
app.include_router(live.router)
app.include_router(admin_panel.router)
app.include_router(feed.router)