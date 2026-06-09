from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Class, Department, SelectedClass, Student
from data.department_seed import SEED_DEPARTMENTS
from data.selected_class_seed import seed_selected_classes
from data.student_seed import SEED_STUDENTS, export_seed_credentials_to_csv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COURSE_DATA_DIR = PROJECT_ROOT / "data" / "course"
DEPARTMENT_CLASS_DATA_DIR = PROJECT_ROOT / "data" / "department_class"
COURSE_SEED_FILENAMES: tuple[str, ...] = (
    "1111.py",
    "1112.py",
    "1121.py",
    "1122.py",
    "1131.py",
    "1132.py",
    "1141.py",
    "1142.py",
    "foreign_language.py",
    "pe.py",
)
DEPARTMENT_CLASS_SEED_FILENAMES: tuple[str, ...] = (
    "business.py",
    "chinese.py",
    "communication.py",
    "computer.py",
    "education.py",
    "foreign.py",
    "international.py",
    "law.py",
    "science.py",
    "social.py",
)


def _load_course_rows_from_file(file_path: Path) -> list[dict[str, Any]]:
    content: str = file_path.read_text(encoding="utf-8")
    match = re.search(r"SEED_CLASSES\s*:[^=]*=\s*(\[)", content)
    if match is None:
        return []

    decoder = json.JSONDecoder()
    try:
        raw_rows, _ = decoder.raw_decode(content[match.start(1) :])
    except json.JSONDecodeError:
        return []

    if not isinstance(raw_rows, list):
        return []
    rows: list[dict[str, Any]] = []
    for item in raw_rows:
        if isinstance(item, dict):
            rows.append(item)
    return rows


def _load_all_course_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for file_name in COURSE_SEED_FILENAMES:
        path = COURSE_DATA_DIR / file_name
        if not path.exists():
            continue
        rows.extend(_load_course_rows_from_file(path))
    for file_name in DEPARTMENT_CLASS_SEED_FILENAMES:
        path = DEPARTMENT_CLASS_DATA_DIR / file_name
        if not path.exists():
            continue
        rows.extend(_load_course_rows_from_file(path))
    return rows


def _seed_departments_once(session: Session) -> tuple[int, int]:
    inserted: int = 0
    skipped: int = 0
    for row in SEED_DEPARTMENTS:
        department_id = int(row["id"])
        existing = session.get(Department, department_id)
        if existing is not None:
            skipped += 1
            continue
        session.add(Department(**row))
        inserted += 1
    session.commit()
    return inserted, skipped


def _seed_students_once(session: Session) -> tuple[int, int]:
    inserted: int = 0
    skipped: int = 0
    for row in SEED_STUDENTS:
        student_id = int(row["id"])
        if session.get(Student, student_id) is not None:
            skipped += 1
            continue
        main_department_id = int(row["main_department_id"])
        if session.get(Department, main_department_id) is None:
            skipped += 1
            continue
        session.add(Student(**row))
        inserted += 1
    session.commit()
    return inserted, skipped


def _seed_courses_once(session: Session) -> tuple[int, int]:
    inserted: int = 0
    skipped: int = 0
    seen_ids: set[int] = set()
    for raw_row in _load_all_course_rows():
        class_id = int(raw_row["id"])
        if class_id in seen_ids:
            skipped += 1
            continue
        seen_ids.add(class_id)

        if session.get(Class, class_id) is not None:
            skipped += 1
            continue
        row: dict[str, Any] = {
            "id": class_id,
            "name": str(raw_row["name"]),
            "credits": int(raw_row["credits"]),
            "requiredOrElectiveCourse": str(raw_row["requiredOrElectiveCourse"]),
            "remark": str(raw_row.get("remark", "")),
            "teacher": str(raw_row["teacher"]),
            "core": bool(raw_row["core"]),
            "academicYearSemester": str(raw_row["academicYearSemester"]),
        }
        session.add(Class(**row))
        inserted += 1
    session.commit()
    return inserted, skipped


def _selected_class_pk_set(session: Session) -> set[tuple[int, int]]:
    rows: list[tuple[int, int]] = list(
        session.query(SelectedClass.classid, SelectedClass.studentid).all()
    )
    return {(int(class_id), int(student_id)) for class_id, student_id in rows}


def _seed_selected_classes_once(session: Session) -> tuple[int, int]:
    before_pk_set: set[tuple[int, int]] = _selected_class_pk_set(session)
    generated_rows: int = seed_selected_classes(
        session=session,
        student_model=Student,
        class_model=Class,
        selected_class_model=SelectedClass,
    )
    after_pk_set: set[tuple[int, int]] = _selected_class_pk_set(session)
    inserted: int = max(len(after_pk_set) - len(before_pk_set), 0)
    skipped: int = max(generated_rows - inserted, 0)
    return inserted, skipped


def seed() -> None:
    session = SessionLocal()
    try:
        steps: list[tuple[str, tuple[int, int]]] = []
        steps.append(("department_seed#1", _seed_departments_once(session)))
        steps.append(("department_seed#2", _seed_departments_once(session)))
        steps.append(("course", _seed_courses_once(session)))
        steps.append(("student_seed", _seed_students_once(session)))
        credential_csv_path: str = export_seed_credentials_to_csv(
            output_path=str(PROJECT_ROOT / "data" / "student_seed_credentials.csv")
        )
        steps.append(("selected_class_seed", _seed_selected_classes_once(session)))

        for label, (inserted, skipped) in steps:
            print(f"[{label}] INSERTED={inserted} SKIPPED={skipped}")
        print(f"[student_seed_credentials] EXPORTED={credential_csv_path}")
    finally:
        session.close()


if __name__ == "__main__":
    seed()
