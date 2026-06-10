from __future__ import annotations

import hashlib
from collections.abc import Mapping

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session, joinedload

from app.core.algorithms import (
    categorize_selection,
    evaluate,
    get_passed_selections,
    get_student,
    parse_categories,
    tally_credits,
)
from app.db.session import SessionLocal
from app.models import Class, Department, SelectedClass, Student

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


def _hash_password(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def _category_to_code(category: str) -> str | None:
    mapping: dict[str, str] = {
        "humanities": "HUM",
        "social": "SOC",
        "sciences": "NAT",
        "computer": "INFO",
        "residential": "COL",
        "chinese": "CHI",
        "english": "ENG",
        "foreign_alt": "ENG",
        "pe": "PE",
    }
    return mapping.get(category)


def _student_profile(student: Student) -> dict[str, object]:
    main_department_name: str = (
        student.main_department.name if student.main_department else "未設定系所"
    )
    tracks: list[str] = []
    if student.secondary_department:
        tracks.append(student.secondary_department.name)
    if student.sub_main1_department:
        tracks.append(student.sub_main1_department.name)
    if student.sub_main2_department:
        tracks.append(student.sub_main2_department.name)
    return {
        "name": student.name,
        "department": main_department_name,
        "double_minor": "、".join(tracks),
        "english_exempt": bool(student.eng_passed),
        "computer_exempt": bool(student.main_department and student.main_department.computer_max == 0),
    }


def _require_login(request: Request, db: Session) -> Student | None:
    student: Student | None = get_current_student(request=request, db=db)
    return student


def _build_detail_items(db: Session, student_id: int) -> list[dict[str, object]]:
    rows: list[SelectedClass] = (
        db.query(SelectedClass)
        .options(joinedload(SelectedClass.class_))
        .filter(SelectedClass.studentid == student_id)
        .all()
    )
    items: list[dict[str, object]] = []
    for selected in rows:
        class_row: Class | None = selected.class_
        if class_row is None:
            continue
        categories: list[str] = parse_categories(class_row.remark)
        primary: str | None = _category_to_code(categories[0]) if categories else None
        secondary: str | None = (
            _category_to_code(categories[1]) if len(categories) > 1 else None
        )
        course_type_raw: str = str(class_row.requiredOrElectiveCourse or "").strip().lower()
        course_type_label: str = (
            "必修" if ("required" in course_type_raw or "必修" in course_type_raw) else "選修"
        )

        is_general_education: bool = primary is not None
        primary_code: str = primary if primary is not None else "OTHER"
        category_display: str = (
            primary_code if is_general_education else (str(class_row.remark or "").strip() or "—")
        )

        score_value = getattr(selected, "score", None)
        score_text: str = f"{float(score_value):.2f}" if score_value is not None else "—"

        items.append(
            {
                "item": {
                    "id": class_row.id,
                    "title": class_row.name,
                    "sub_category": primary_code,
                    "alt_category": secondary,
                    "is_core": bool(class_row.core),
                    "credits": int(class_row.credits),
                    "is_general_education": is_general_education,
                    "category_display": category_display,
                    "course_type_label": course_type_label,
                    "teacher": str(class_row.teacher or "—"),
                    "academic_year_semester": str(class_row.academicYearSemester or "—"),
                    "score_text": score_text,
                },
                "passed": bool(selected.ispassed),
            }
        )
    return items


def _result_context(
    db: Session,
    student: Student,
    override_map: Mapping[int, str] | None = None,
) -> dict[str, int]:
    passed_rows: list[SelectedClass] = get_passed_selections(db=db, student_id=student.id)
    for selected in passed_rows:
        category_override: str | None = None
        if override_map is not None:
            category_override = override_map.get(int(selected.classid))
        if category_override is not None:
            setattr(selected, "chosen_category", category_override)

    department: Department | None = student.main_department or db.get(
        Department, student.main_department_id
    )
    if department is None:
        return _demo_dashboard_context()

    credits, core_categories, pe_courses, foreign_pair = tally_credits(
        selections=passed_rows,
        student=student,
        department=department,
    )
    core_credit_map: dict[str, int] = {
        "humanities": 0,
        "social": 0,
        "sciences": 0,
    }
    for selected in passed_rows:
        class_row: Class | None = selected.class_
        if class_row is None or not bool(class_row.core):
            continue
        category = categorize_selection(class_row, selected)
        if category in core_credit_map:
            core_credit_map[category] += int(class_row.credits)

    result: dict[str, object] = evaluate(
        credits=credits,
        core_categories=core_categories,
        pe_courses=pe_courses,
        department=department,
        foreign_pair=foreign_pair,
    )

    categories: Mapping[str, Mapping[str, int]] = result["categories"]  # type: ignore[assignment]
    return {
        "total_counted_credits": int(result["total_excluding_pe"]["counted"]),  # type: ignore[index]
        "humanities_credits": int(categories["humanities"]["counted"]),
        "humanities_core_credits": core_credit_map["humanities"],
        "social_credits": int(categories["social"]["counted"]),
        "social_core_credits": core_credit_map["social"],
        "natural_credits": int(categories["sciences"]["counted"]),
        "natural_core_credits": core_credit_map["sciences"],
        "info_credits": 0 if department.computer_max == 0 else int(categories["computer"]["counted"]),
        "college_credits": int(categories["residential"]["counted"]),
        "chinese_credits": int(categories["chinese"]["counted"]),
        "english_credits": int(categories["english"]["counted"]),
        "pe_credits": int(pe_courses),
        "computer_exempt": bool(department.computer_max == 0),
        "english_exempt": bool(student.eng_passed),
    }


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
        {"request": request, "error": None},
    )


@router.post("/login")
async def login_submit(
    request: Request,
    student_no: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    try:
        student_id: int = int(student_no)
    except ValueError:
        return request.app.state.templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "帳號或密碼錯誤"},
            status_code=400,
        )

    student: Student | None = db.get(Student, student_id)
    if student is None or student.hashed_password != _hash_password(password):
        return request.app.state.templates.TemplateResponse(
            "login.html",
            {"request": request, "error": "帳號或密碼錯誤"},
            status_code=400,
        )

    request.session["student_id"] = student.id
    return RedirectResponse(url="/details", status_code=303)


@router.get("/dashboard")
async def dashboard():
    return RedirectResponse(url="/details", status_code=302)


@router.get("/details")
async def details(request: Request, db: Session = Depends(get_db)):
    student: Student | None = _require_login(request=request, db=db)
    if student is None:
        return RedirectResponse(url="/login", status_code=302)

    return request.app.state.templates.TemplateResponse(
        "details.html",
        {
            "request": request,
            "student": _student_profile(student),
            "items": _build_detail_items(db=db, student_id=student.id),
        },
    )


@router.post("/results")
async def results(request: Request, db: Session = Depends(get_db)):
    student: Student | None = _require_login(request=request, db=db)
    if student is None:
        return RedirectResponse(url="/login", status_code=302)

    form = await request.form()
    override_map: dict[int, str] = {}
    for key, value in form.items():
        if not key.startswith("dual_"):
            continue
        raw_class_id: str = key.replace("dual_", "", 1)
        try:
            class_id = int(raw_class_id)
        except ValueError:
            continue
        normalized = _category_to_code(value)
        canonical_map: dict[str, str] = {
            "HUM": "humanities",
            "SOC": "social",
            "NAT": "sciences",
            "INFO": "computer",
            "COL": "residential",
            "CHI": "chinese",
            "ENG": "english",
            "PE": "pe",
        }
        if normalized is None:
            normalized = value if isinstance(value, str) else None
        canonical = canonical_map.get(normalized) if normalized else None
        if canonical is not None:
            override_map[class_id] = canonical

    context: dict[str, object] = {
        "request": request,
        "student": _student_profile(student),
    }
    context.update(_result_context(db=db, student=student, override_map=override_map))
    return request.app.state.templates.TemplateResponse("results.html", context)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)
