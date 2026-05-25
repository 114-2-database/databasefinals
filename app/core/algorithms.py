"""Graduation credit audit helpers.

The public entry point is :func:`calculate_score`. Given a database session
and a student id, it inspects the student's passed classes and the
requirements of their main department and reports progress against every
general-education category, plus PE and the overall total.

A class's ``remark`` may now list up to three GE categories separated by
``、`` or ``,`` (e.g. ``"社會通、人文通"``). The class's credits count toward
exactly one of those categories — the one the student picked. The pick is
read from ``SelectedClass.chosen_category`` (a string, holding either a
canonical category key like ``"social"`` or the Chinese label like
``"社會通"``). If the column is absent or unset, the first listed category
is used as a fallback so credits are never silently dropped.

Router usage::

    from app.core.algorithms import calculate_score

    @router.get("/calculate")
    async def calculate(request: Request, db: Session = Depends(get_db)):
        student_id = request.session.get("student_id")
        if not student_id:
            return {"error": "User not logged in"}
        return calculate_score(db, student_id)

NOTE: this module expects ``SelectedClass.chosen_category: str | None`` to
exist on the model. Until that column is added, every multi-category class
will fall back to its first listed category.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable

from sqlalchemy.orm import Session, joinedload

from app.models import Class, Department, SelectedClass, Student


# --- Category keys -----------------------------------------------------------

HUMANITIES = "humanities"
SOCIAL = "social"
SCIENCES = "sciences"
COMPUTER = "computer"
RESIDENTIAL = "residential"
CHINESE = "chinese"
ENGLISH = "english"          # 大學英文 — counted unless eng_passed
FOREIGN_ALT = "foreign_alt"  # 大學外文 — counted only if eng_passed
PE = "pe"


# Map of normalized remark text → canonical category. Lookups are
# case-insensitive after stripping whitespace, so each surface form only
# needs to appear once. Includes the canonical keys themselves so a
# ``chosen_category`` value of ``"social"`` resolves just like ``"社會通"``.
_REMARK_TO_CATEGORY: dict[str, str] = {
    # 人文通識
    "hum": HUMANITIES, "humanities": HUMANITIES,
    "人文": HUMANITIES, "人文通": HUMANITIES, "人文通識": HUMANITIES,
    # 社會通識
    "soc": SOCIAL, "social": SOCIAL,
    "社會": SOCIAL, "社會通": SOCIAL, "社會通識": SOCIAL,
    # 自然通識
    "nat": SCIENCES, "sciences": SCIENCES, "natural": SCIENCES,
    "自然": SCIENCES, "自然通": SCIENCES, "自然通識": SCIENCES,
    # 資訊通識 — covers both 純資訊 and 跨領域 listings. The 跨領域 vs
    # 非跨領域 distinction is now derived from how many categories the
    # remark lists, so a dedicated COMPUTER_CROSS key is no longer needed.
    "info": COMPUTER, "computer": COMPUTER,
    "資訊": COMPUTER, "資訊通": COMPUTER, "資訊通識": COMPUTER,
    "跨領域資訊": COMPUTER, "跨領域資訊通": COMPUTER, "跨領域資訊通識": COMPUTER,
    # 書院通識
    "res": RESIDENTIAL, "residential": RESIDENTIAL, "college": RESIDENTIAL,
    "書院": RESIDENTIAL, "書院通": RESIDENTIAL, "書院通識": RESIDENTIAL,
    # 中文通識
    "chi": CHINESE, "chinese": CHINESE,
    "中文": CHINESE, "中文通": CHINESE, "中文通識": CHINESE, "大學中文": CHINESE,
    # 大學英文
    "eng": ENGLISH, "english": ENGLISH,
    "英文": ENGLISH, "大學英文": ENGLISH,
    # 大學外文 — used to fulfil English requirement when student is exempt
    "foreign": FOREIGN_ALT, "foreign_alt": FOREIGN_ALT,
    "外文": FOREIGN_ALT, "大學外文": FOREIGN_ALT,
    # 體育
    "pe": PE, "體育": PE,
}


# Accept Chinese 、, Chinese ，, ASCII , or whitespace runs as separators.
_REMARK_SPLIT_RE = re.compile(r"[、，,/]+|\s{2,}")


def _normalize(text: str | None) -> str | None:
    if not text:
        return None
    return _REMARK_TO_CATEGORY.get(text.strip().lower())


def parse_categories(remark: str | None) -> list[str]:
    """Split a class remark into its listed canonical categories.

    A remark may hold up to three categories separated by ``、`` or ``,``
    (e.g. ``"社會通、人文通"``). Unrecognised tokens are silently dropped,
    and duplicates are removed while preserving order.
    """
    if not remark:
        return []
    seen: list[str] = []
    for token in _REMARK_SPLIT_RE.split(remark):
        category = _normalize(token)
        if category and category not in seen:
            seen.append(category)
    return seen


def categorize_selection(
    class_: Class | None, selected: SelectedClass | None
) -> str | None:
    """Return which GE category this selection's credits count toward.

    Resolution order:
    1. If ``SelectedClass.chosen_category`` is set and matches one of the
       categories listed in the class's remark, use it.
    2. Otherwise fall back to the first listed category, so credits are
       never silently dropped just because the student hasn't picked yet.
    3. If the remark has no recognisable category at all, return ``None``.
    """
    options = parse_categories(class_.remark) if class_ else []
    if not options:
        return None

    chosen_raw = getattr(selected, "chosen_category", None) if selected else None
    chosen = _normalize(chosen_raw)
    if chosen and chosen in options:
        return chosen

    return options[0]


# --- Exemption helpers -------------------------------------------------------

def is_exempt_from_computer(department: Department | None) -> bool:
    # Departments whose own curriculum already covers 資訊 (統計、資管、
    # 應數、資科、地政測資組…) are encoded by setting ``computer_max`` to 0
    # — i.e. no 資訊通識 credits may count toward their students' total.
    return department is not None and department.computer_max == 0


def is_exempt_from_english(student: Student) -> bool:
    return bool(student.eng_passed)


# --- Database lookups --------------------------------------------------------

def get_student(db: Session, student_id: int) -> Student | None:
    return db.query(Student).filter(Student.id == student_id).first()


def get_passed_selections(db: Session, student_id: int) -> list[SelectedClass]:
    """Fetch every passed ``SelectedClass`` row with its ``Class`` eagerly
    joined, so the caller can read both the class metadata (credits, remark,
    core) and the student's ``chosen_category`` without N+1 queries."""
    return (
        db.query(SelectedClass)
        .options(joinedload(SelectedClass.class_))
        .filter(
            SelectedClass.studentid == student_id,
            SelectedClass.ispassed.is_(True),
        )
        .all()
    )


# --- Aggregation -------------------------------------------------------------

@dataclass
class CategoryStatus:
    earned: int
    counted: int        # earned capped at ``maximum``
    required: int
    maximum: int | None
    met: bool
    shortfall: int


@dataclass
class PEStatus:
    earned_courses: int
    required_courses: int
    met: bool
    shortfall: int


def _empty_credits() -> dict[str, int]:
    return {
        HUMANITIES: 0, SOCIAL: 0, SCIENCES: 0, COMPUTER: 0,
        RESIDENTIAL: 0, CHINESE: 0, ENGLISH: 0,
    }


def tally_credits(
    selections: Iterable[SelectedClass],
    student: Student,
    department: Department,
) -> tuple[dict[str, int], dict[str, int], int]:
    """Walk a student's passed selections and bucket their credits.

    For each selection we look up the student's chosen category (or the
    first-listed fallback) and route the class's credits into one bucket
    only, applying the exemption rules:

    * 資訊 (chosen, single- or multi-category) → skipped if the dept is
      computer-exempt; otherwise counted toward ``computer``.
    * 大學英文 → skipped if the student is English-exempt; otherwise
      counted toward ``english``.
    * 大學外文 → only counted (toward ``english``) if the student is
      English-exempt; ignored otherwise.
    * PE → counted as a course toward ``pe_courses`` (not credits).
    * everything else → counted toward its chosen category.

    Returns ``(credits, core_credits, pe_courses)``.
    """
    credits = _empty_credits()
    core_credits = _empty_credits()
    pe_courses = 0

    computer_exempt = is_exempt_from_computer(department)
    english_exempt = is_exempt_from_english(student)

    for selected in selections:
        class_ = selected.class_
        if class_ is None:
            continue

        category = categorize_selection(class_, selected)
        if category is None:
            continue

        if category == PE:
            pe_courses += 1
            continue

        if category == COMPUTER:
            if computer_exempt:
                continue
            bucket = COMPUTER
        elif category == ENGLISH:
            if english_exempt:
                continue
            bucket = ENGLISH
        elif category == FOREIGN_ALT:
            if not english_exempt:
                continue
            bucket = ENGLISH
        else:
            bucket = category

        credits[bucket] += class_.credits
        if class_.core:
            core_credits[bucket] += class_.credits

    return credits, core_credits, pe_courses


# --- Requirement evaluation --------------------------------------------------

# School-wide minimum, excluding PE.
TOTAL_REQUIRED_EXCLUDING_PE = 28


def _status(earned: int, required: int, maximum: int | None) -> CategoryStatus:
    counted = earned if maximum is None else min(earned, maximum)
    return CategoryStatus(
        earned=earned,
        counted=counted,
        required=required,
        maximum=maximum,
        met=earned >= required,
        shortfall=max(required - earned, 0),
    )


def evaluate(
    credits: dict[str, int],
    pe_courses: int,
    department: Department,
) -> dict:
    """Compare aggregated credits against the department's requirements."""
    categories: dict[str, CategoryStatus] = {
        # ``humanities`` and ``foreign`` are stored as single integers on
        # the department row — treat them as the minimum required, with
        # no upper cap.
        HUMANITIES: _status(credits[HUMANITIES], department.humanities, None),
        SOCIAL: _status(credits[SOCIAL], department.social_min, department.social_max),
        SCIENCES: _status(credits[SCIENCES], department.sciences_min, department.sciences_max),
        COMPUTER: _status(credits[COMPUTER], department.computer_min, department.computer_max),
        RESIDENTIAL: _status(
            credits[RESIDENTIAL], department.residential_min, department.residential_max
        ),
        CHINESE: _status(credits[CHINESE], department.chinese_min, department.chinese_max),
        ENGLISH: _status(credits[ENGLISH], department.foreign, None),
    }

    pe_status = PEStatus(
        earned_courses=pe_courses,
        required_courses=department.pe,
        met=pe_courses >= department.pe,
        shortfall=max(department.pe - pe_courses, 0),
    )

    # Total excluding PE: sum each bucket capped at its ``maximum``, so
    # over-earning in one area cannot paper over a deficit in another.
    counted_total = sum(s.counted for s in categories.values())
    total_status = CategoryStatus(
        earned=sum(credits.values()),
        counted=counted_total,
        required=TOTAL_REQUIRED_EXCLUDING_PE,
        maximum=None,
        met=counted_total >= TOTAL_REQUIRED_EXCLUDING_PE,
        shortfall=max(TOTAL_REQUIRED_EXCLUDING_PE - counted_total, 0),
    )

    return {
        "categories": {k: asdict(v) for k, v in categories.items()},
        "pe": asdict(pe_status),
        "total_excluding_pe": asdict(total_status),
        "graduation_ready": (
            all(s.met for s in categories.values())
            and pe_status.met
            and total_status.met
        ),
    }


# --- Public entry point ------------------------------------------------------

def calculate_score(db: Session, student_id: int) -> dict:
    """Compute graduation audit information for ``student_id``.

    Returns a JSON-serialisable dictionary containing per-category credit
    counts, whether each requirement is met, the PE course count, and the
    overall total.
    """
    student = get_student(db, student_id)
    if student is None:
        return {"error": "student not found", "student_id": student_id}

    department = student.main_department or (
        db.query(Department)
        .filter(Department.id == student.main_department_id)
        .first()
    )
    if department is None:
        return {"error": "department not found", "student_id": student_id}

    selections = get_passed_selections(db, student_id)
    credits, core_credits, pe_courses = tally_credits(selections, student, department)
    result = evaluate(credits, pe_courses, department)
    result["student_id"] = student.id
    result["main_department_id"] = department.id
    result["core_credits"] = core_credits
    return result
