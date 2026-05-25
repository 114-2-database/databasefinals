from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
# from app.models import CheckItem, Student, StudentCheckItem
from app.models import Student

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_student(request: Request, db: Session) -> Student | None:
    student_id = request.session.get("student_id")
    if not student_id:
        return None
    return db.query(Student).filter(Student.id == student_id).first()


@router.get("/")
async def root():
    return RedirectResponse(url="/login", status_code=302)


def _demo_student() -> dict:
    return {
        "name": "Demo Student",
        "department": "General Studies",
        "double_minor": "",
    }


def _demo_dashboard_context() -> dict:
    return {
        "total_counted_credits": 0,
        "humanities_credits": 0,
        "humanities_core_credits": 0,
        "social_credits": 0,
        "social_core_credits": 0,
        "natural_credits": 0,
        "natural_core_credits": 0,
        "info_credits": 0,
        "college_credits": 0,
        "chinese_credits": 0,
        "english_credits": 0,
        "pe_credits": 0,
    }


@router.get("/login")
async def login(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html",
        {"request": request},
    )


@router.get("/dashboard")
async def dashboard(request: Request):
    context = {"request": request, "student": _demo_student()}
    context.update(_demo_dashboard_context())
    return request.app.state.templates.TemplateResponse("dashboard.html", context)


@router.get("/details")
async def details(request: Request):
    return request.app.state.templates.TemplateResponse(
        "details.html",
        {"request": request, "student": _demo_student(), "items": []},
    )


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
