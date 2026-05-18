from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import SESSION_SECRET
from app.routers import auth, pages

app = FastAPI(title="NCCU 畢業離校檢核 通識體育版")

app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET)

app.mount("/static", StaticFiles(directory="app/static"), name="static")
app.state.templates = Jinja2Templates(directory="app/templates")

app.include_router(auth.router)
app.include_router(pages.router)
