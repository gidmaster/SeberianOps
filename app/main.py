from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from app.config import settings
from app.routers import blog

app = FastAPI(title=settings.app_title)

app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(blog.router)
