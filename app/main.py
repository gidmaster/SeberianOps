from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import HTTPException
from app.config import settings
from app.routers import admin, blog, feed
from app.errors import http_exception_handler, server_error_handler

app = FastAPI(title=settings.app_title)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, server_error_handler)

app.include_router(blog.router)
app.include_router(admin.router)
app.include_router(feed.router)
