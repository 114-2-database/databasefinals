from fastapi import APIRouter, Depends, Request
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


# @router.get("/dashboard")
# async def dashboard(request: Request, db: Session = Depends(get_db)):
#     student = get_current_student(request, db)
#     if not student:
#         return RedirectResponse(url="/login", status_code=302)

#     items = (
#         db.query(StudentCheckItem)
#         .join(CheckItem, StudentCheckItem.item_id == CheckItem.id)
#         .filter(StudentCheckItem.student_id == student.id)
#         .all()
#     )
#     ge_total = sum(1 for i in items if i.item.category == "GE")
#     ge_passed = sum(1 for i in items if i.item.category == "GE" and i.passed)
#     pe_total = sum(1 for i in items if i.item.category == "PE")
#     pe_passed = sum(1 for i in items if i.item.category == "PE" and i.passed)

#     return request.app.state.templates.TemplateResponse(
#         "dashboard.html",
#         {
#             "request": request,
#             "student": student,
#             "ge_total": ge_total,
#             "ge_passed": ge_passed,
#             "pe_total": pe_total,
#             "pe_passed": pe_passed,
#         },
#     )


# @router.get("/details")
# async def details(request: Request, db: Session = Depends(get_db)):
#     student = get_current_student(request, db)
#     if not student:
#         return RedirectResponse(url="/login", status_code=302)

#     items = (
#         db.query(StudentCheckItem)
#         .join(CheckItem, StudentCheckItem.item_id == CheckItem.id)
#         .filter(StudentCheckItem.student_id == student.id)
#         .all()
#     )
#     return request.app.state.templates.TemplateResponse(
#         "details.html",
#         {"request": request, "student": student, "items": items},
#     )
