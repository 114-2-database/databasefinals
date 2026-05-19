import hashlib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Student

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/login")
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    student_no: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    hashed = hash_password(password)
    student = (
        db.query(Student)
        .filter(Student.student_no == student_no, Student.password_hash == hashed)
        .first()
    )
    if not student:
        return request.app.state.templates.TemplateResponse(
            "login.html", {"request": request, "error": "帳號或密碼錯誤"}
        )
    request.session["student_id"] = student.id
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
