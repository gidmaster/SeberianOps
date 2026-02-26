from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.httpsredirect import HTTPSRedirectMiddleware
from fastapi.exceptions import HTTPException
from app.config import settings
from app.routers import blog, admin, feed, live
from app.errors import http_exception_handler, server_error_handler
from app.database.engine import engine
from app.database.base import Base
from app.database.models import post_stat  # noqa: F401 - registers model

@asynccontextmanager
async def lifespan(app: FastAPI):
    yield
    # Shutdown
    await engine.dispose()

app = FastAPI(title=settings.app_title, lifespan=lifespan)

if settings.app_env == "production":
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, server_error_handler)

app.include_router(blog.router)
app.include_router(admin.router)
app.include_router(feed.router)
app.include_router(live.router)