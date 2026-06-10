"""Selected-class seed generator for importing in main project.

How to use in your main project:
    from data.selected_class_seed import seed_selected_classes
    from your_project.database import SessionLocal
    from your_project.students import Student
    from your_project.model import Class
    from your_project.selected_class import SelectedClass

    with SessionLocal() as session:
        total = seed_selected_classes(
            session=session,
            student_model=Student,
            class_model=Class,
            selected_class_model=SelectedClass,
        )
        print(total)
"""

from __future__ import annotations

import re
import random
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

# ---------------------------------------------------------------------------
# Lightweight remark parser (mirrors app.core.algorithms logic)
# ---------------------------------------------------------------------------

_REMARK_SPLIT_RE = re.compile(r"[、，,/（）()]+|\s{2,}")

_REMARK_TO_CATEGORY: dict[str, str] = {
    "hum": "humanities", "humanities": "humanities",
    "人文": "humanities", "人文通": "humanities", "人文通識": "humanities",
    "soc": "social", "social": "social",
    "社會": "social", "社會通": "social", "社會通識": "social",
    "nat": "sciences", "sciences": "sciences", "natural": "sciences",
    "自然": "sciences", "自然通": "sciences", "自然通識": "sciences",
    "info": "computer", "computer": "computer",
    "資訊": "computer", "資訊通": "computer", "資訊通識": "computer",
    "跨領域資訊": "computer", "跨領域資訊通": "computer", "跨領域資訊通識": "computer",
    "res": "residential", "residential": "residential", "college": "residential",
    "書院": "residential", "書院通": "residential", "書院通識": "residential",
    "chi": "chinese", "chinese": "chinese",
    "中文": "chinese", "中文通": "chinese", "中文通識": "chinese", "大學中文": "chinese",
    "eng": "english", "english": "english",
    "英文": "english", "大學英文": "english",
    "foreign": "foreign_alt", "foreign_alt": "foreign_alt",
    "外文": "foreign_alt", "大學外文": "foreign_alt", "外文通識": "foreign_alt",
    "pe": "pe", "體育": "pe",
}


def _parse_categories(remark: str | None) -> list[str]:
    """Return the list of standard category keys found in a remark string."""
    if not remark:
        return []
    seen: list[str] = []
    for token in _REMARK_SPLIT_RE.split(remark):
        cat = _REMARK_TO_CATEGORY.get(token.strip().lower())
        if cat and cat not in seen:
            seen.append(cat)
    return seen

SEMESTERS: tuple[str, ...] = ("1111", "1112", "1121", "1122", "1131", "1132", "1141", "1142")
RANDOM_SEED: int = 20260609

_RNG = random.Random(RANDOM_SEED)


@dataclass(frozen=True)
class CourseInfo:
    """Course snapshot used for random selection."""

    class_id: int
    name: str
    credits: int
    semester: str
    remark: str  # raw remark from Class.remark; used to detect cross-domain courses


def _admission_year(student_id: int) -> int:
    """Get admission year from student id prefix.

    Args:
        student_id: Student id (first 3 digits are admission year).

    Returns:
        Admission year.
    """
    return int(str(student_id)[:3])


def _eligible_semesters(student_id: int) -> list[str]:
    """Get available semesters for a student by admission year.

    Args:
        student_id: Student id.

    Returns:
        Eligible semester list.
    """
    year: int = _admission_year(student_id)
    if year <= 111:
        return list(SEMESTERS)
    if year == 112:
        return [semester for semester in SEMESTERS if semester >= "1121"]
    if year == 113:
        return [semester for semester in SEMESTERS if semester >= "1131"]
    return [semester for semester in SEMESTERS if semester >= "1141"]


def _is_multi_track_student(student: Any) -> bool:
    """Check whether student has double-major or minor.

    Args:
        student: Student ORM row.

    Returns:
        True if student has any additional track.
    """
    return any(
        (
            getattr(student, "sec_main_department_id", None) is not None,
            getattr(student, "sub_main1_department_id", None) is not None,
            getattr(student, "sub_main2_department_id", None) is not None,
        )
    )


def _target_credit_range(student: Any, semester: str) -> tuple[int, int]:
    """Get target credit range for one student in one semester.

    Rule summary:
    - Around 90% below 25 credits.
    - Around 10% between 25 and 30 credits.
    - Heavy load is more likely for students with double-major/minor.

    Args:
        student: Student ORM row.
        semester: Semester string, e.g. "1132".

    Returns:
        (min_credits, max_credits) for this semester.
    """
    multi_track: bool = _is_multi_track_student(student)
    has_double_major: bool = getattr(student, "sec_main_department_id", None) is not None
    minor_count: int = int(getattr(student, "sub_main1_department_id", None) is not None) + int(
        getattr(student, "sub_main2_department_id", None) is not None
    )

    high_load_probability: float = 0.05
    if multi_track:
        high_load_probability = 0.15
    if has_double_major and minor_count >= 1:
        high_load_probability = 0.22
    elif minor_count == 2:
        high_load_probability = 0.18

    semester_index: int = SEMESTERS.index(semester)
    admission_index: int = SEMESTERS.index(_eligible_semesters(int(student.id))[0])
    relative_semester: int = semester_index - admission_index

    # First year generally has a slightly lower average load.
    is_early_stage: bool = relative_semester <= 1
    if _RNG.random() < high_load_probability:
        return (25, 30)
    if is_early_stage:
        return (14, 22)
    return (15, 24)


def _pick_courses_for_semester(
    courses: list[CourseInfo],
    min_target: int,
    max_target: int,
    selected_class_ids: set[int],
    blocked_course_names: set[str],
) -> list[CourseInfo]:
    """Pick courses up to target credits with slight randomization.

    Args:
        courses: Candidate courses for one semester.
        min_target: Minimum desired credits.
        max_target: Maximum desired credits.
        selected_class_ids: Class ids already selected by this student.
        blocked_course_names: Course names that cannot be selected.

    Returns:
        Picked course list.
    """
    candidates: list[CourseInfo] = [course for course in courses if course.class_id not in selected_class_ids]
    _RNG.shuffle(candidates)

    picked: list[CourseInfo] = []
    picked_course_names: set[str] = set()
    total_credits: int = 0
    soft_upper: int = max_target

    for course in candidates:
        if course.name in blocked_course_names:
            continue
        # Different teachers opening the same course name in one semester count as one choice.
        if course.name in picked_course_names:
            continue
        if total_credits + course.credits > soft_upper:
            continue
        picked.append(course)
        selected_class_ids.add(course.class_id)
        picked_course_names.add(course.name)
        total_credits += course.credits

        if total_credits >= min_target:
            # Stop with high probability to keep loads diverse.
            if _RNG.random() < 0.85:
                break

    # Guarantee a floor load when possible: try to reach min_target even if
    # the first pass stopped early due randomization or upper-bound filtering.
    if total_credits < min_target:
        for course in candidates:
            if course.class_id in selected_class_ids:
                continue
            if course.name in blocked_course_names:
                continue
            if course.name in picked_course_names:
                continue
            picked.append(course)
            selected_class_ids.add(course.class_id)
            picked_course_names.add(course.name)
            total_credits += course.credits
            if total_credits >= min_target:
                break

    # Last-resort fallback: if still below 12 credits due blocked names,
    # allow previously blocked names to satisfy semester minimum.
    hard_minimum: int = 12
    if total_credits < hard_minimum:
        for course in candidates:
            if course.class_id in selected_class_ids:
                continue
            if course.name in picked_course_names:
                continue
            picked.append(course)
            selected_class_ids.add(course.class_id)
            picked_course_names.add(course.name)
            total_credits += course.credits
            if total_credits >= hard_minimum:
                break

    return picked


def _score_and_pass(semester: str) -> tuple[bool, Decimal]:
    """Generate pass flag and score by semester recency.

    Args:
        semester: Academic year semester code.

    Returns:
        (ispassed, score).
    """
    latest_semester: str = "1142"
    if semester < latest_semester:
        pass_probability: float = 0.88
    else:
        pass_probability = 0.78

    is_passed: bool = _RNG.random() < pass_probability
    if is_passed:
        score_value: float = round(_RNG.uniform(60.0, 99.0), 2)
    else:
        score_value = round(_RNG.uniform(0.0, 59.0), 2)
    return is_passed, Decimal(str(score_value))


def seed_selected_classes(
    session: Any,
    student_model: type[Any],
    class_model: type[Any],
    selected_class_model: type[Any],
) -> int:
    """Generate selected-class rows from existing students and classes.

    This function reads students from database (assumes `student_seed.py` has
    been seeded already), then assigns courses by semester according to:
    - Student admission year from first 3 digits of student id.
    - About 90% semester loads below 25 credits.
    - About 10% semester loads in 25-30 credits, mostly multi-track students.
    - Foreign-language and advanced English courses are all allowed.

    Args:
        session: SQLAlchemy session instance.
        student_model: Student ORM model class.
        class_model: Class ORM model class.
        selected_class_model: SelectedClass ORM model class.

    Returns:
        Number of processed selected-class rows.
    """
    students: list[Any] = list(session.query(student_model).all())
    classes: list[Any] = list(session.query(class_model).all())

    semester_courses: dict[str, list[CourseInfo]] = defaultdict(list)
    class_map: dict[int, CourseInfo] = {}
    for class_row in classes:
        semester: str = str(getattr(class_row, "academicYearSemester", ""))
        if semester not in SEMESTERS:
            continue
        try:
            class_id: int = int(getattr(class_row, "id"))
            credits: int = int(getattr(class_row, "credits"))
            class_name: str = str(getattr(class_row, "name", "")).strip()
            remark: str = str(getattr(class_row, "remark", "") or "")
        except (TypeError, ValueError):
            continue
        course = CourseInfo(
            class_id=class_id,
            name=class_name,
            credits=credits,
            semester=semester,
            remark=remark,
        )
        semester_courses[semester].append(course)
        class_map[class_id] = course

    existing_rows: list[Any] = list(session.query(selected_class_model).all())
    existing_map: dict[tuple[int, int], Any] = {
        (int(row.studentid), int(row.classid)): row for row in existing_rows
    }
    existing_rows_by_student: dict[int, list[Any]] = defaultdict(list)
    for row in existing_rows:
        existing_rows_by_student[int(row.studentid)].append(row)

    processed: int = 0
    for student in students:
        student_id: int = int(getattr(student, "id"))
        eligible_semesters: list[str] = _eligible_semesters(student_id=student_id)
        selected_class_ids: set[int] = set()
        passed_course_names: set[str] = set()

        # Keep previously passed course names blocked when reseeding.
        for existing in existing_rows_by_student.get(student_id, []):
            if int(existing.studentid) != student_id or not bool(existing.ispassed):
                continue
            existing_course = class_map.get(int(existing.classid))
            if existing_course is not None and existing_course.name:
                passed_course_names.add(existing_course.name)

        for semester in eligible_semesters:
            courses: list[CourseInfo] = semester_courses.get(semester, [])
            if not courses:
                continue

            min_target, max_target = _target_credit_range(student=student, semester=semester)
            min_target = max(min_target, 12)
            picked_courses: list[CourseInfo] = _pick_courses_for_semester(
                courses=courses,
                min_target=min_target,
                max_target=max_target,
                selected_class_ids=selected_class_ids,
                blocked_course_names=passed_course_names,
            )

            for course in picked_courses:
                is_passed, score = _score_and_pass(semester=semester)
                key: tuple[int, int] = (student_id, course.class_id)
                existing = existing_map.get(key)
                if existing is None:
                    # For cross-domain courses (remark lists 2+ categories),
                    # randomly assign chosen_category so students can be
                    # distributed across valid options.  Single-category or
                    # unrecognised courses keep chosen_category = None, which
                    # causes algorithms.py to fall back to the first listed
                    # category automatically.
                    categories: list[str] = _parse_categories(course.remark)
                    chosen_category: str | None = None
                    if len(categories) >= 2:
                        chosen_category = _RNG.choice(categories)

                    session.add(
                        selected_class_model(
                            classid=course.class_id,
                            studentid=student_id,
                            ispassed=is_passed,
                            score=score,
                            chosen_category=chosen_category,
                        )
                    )
                    existing_map[key] = True
                    if is_passed:
                        passed_course_names.add(course.name)
                    processed += 1

    session.commit()
    return processed
