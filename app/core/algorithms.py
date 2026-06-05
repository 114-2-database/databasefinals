"""
畢業學分審核工具

主要入口為 :func:`calculate_score`，傳入資料庫 session 與學生 ID，
讀取該學生的修課紀錄與所屬科系的畢業門檻，回傳各通識類別、體育及總學分的達標狀況。

課程的 ``remark`` 欄位可用 ``、`` 或 ``,`` 列出最多三個通識類別（例如 ``"社會通、人文通"``）。
學分只能計入其中一個類別，由 ``SelectedClass.chosen_category`` 決定（可填類別代號如
``"social"``，或中文名稱如 ``"社會通"``）。若該欄位尚未設定，則自動採用 remark 中
第一個類別作為預設值，避免學分被忽略。

Router 使用範例:

    from app.core.algorithms import calculate_score

    @router.get("/calculate")
    async def calculate(request: Request, db: Session = Depends(get_db)):
        student_id = request.session.get("student_id")
        if not student_id:
            return {"error": "User not logged in"}
        return calculate_score(db, student_id)

NOTE/TODO: 
    - 需要 ``SelectedClass.chosen_category: str | None`` 欄位存在於 model 中
      (在該欄位加入之前，所有多類別課程將自動採用第一個列出的類別)
    
    - 沒有 min & max 版本的通識種類都暫時被當 min (如: humanities 和 foreign)

    - ER-Diagram 裡面用 collegeEnglishExemption 來表示大學英文免修，但在 model 裡面用 eng_passed 來表示，所以這邊暫時用 eng_passed
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

# 比對大學外文課程名稱，抓出學期和語種，例如 "大學外文（一）：日文" → ("一", "日文")
_FOREIGN_LANG_RE = re.compile(r"大學外文（([一二])）：(.+)")


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


def _parse_foreign_lang(name: str | None) -> tuple[str, str] | None:
    """從大學外文課程名稱解析出學期和語種。

    例如 "大學外文（一）：日文" → ("一", "日文")
    無法解析（非外文課程格式）則回傳 None。
    """
    if not name:
        return None
    m = _FOREIGN_LANG_RE.match(name.strip())
    if m:
        return m.group(1), m.group(2)  # (學期, 語種)
    return None


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


@dataclass
class CoreGEStatus:
    # Number of distinct GE categories (人文/社會/自然) where the student
    # has passed at least one 核心通識 course.
    earned_categories: int
    required_categories: int
    earned_category_list: list   # which category keys are covered
    met: bool
    shortfall: int


@dataclass
class ForeignPairStatus:
    # 免修大學英文者需以「同語種大學外文（一）＋（二）」補足 6 學分。
    # 僅在 student.eng_passed = True 時有意義。
    language: str | None        # 配對成功的語種（如 "日文"）；無有效配對則為 None
    has_first_sem: bool         # 是否有（一）
    has_second_sem: bool        # 是否有（二）
    valid: bool                 # （一）和（二）皆有，且同語種，才算有效
    credits: int                # 計入 english bucket 的學分（無效配對為 0）


# Only 人文、社會、自然 have 核心通識 courses.
_CORE_GE_BUCKETS: frozenset[str] = frozenset({HUMANITIES, SOCIAL, SCIENCES})

CORE_GE_REQUIRED = 2


def _empty_credits() -> dict[str, int]:
    return {
        HUMANITIES: 0, SOCIAL: 0, SCIENCES: 0, COMPUTER: 0,
        RESIDENTIAL: 0, CHINESE: 0, ENGLISH: 0,
    }


def _validate_foreign_pair(foreign_classes: list[Class]) -> ForeignPairStatus:
    """驗證大學外文課程是否符合「同語種（一）＋（二）」規則。

    將傳入的外文課按語種分組，找到第一個同時有（一）和（二）的語種視為有效配對。
    若無有效配對，回傳進度最近的語種狀態（credits = 0）。
    """
    # {語種: {學期: 學分}}，例如 {"日文": {"一": 3, "二": 3}}
    groups: dict[str, dict[str, int]] = {}
    for cls in foreign_classes:
        parsed = _parse_foreign_lang(cls.name)
        if not parsed:
            continue
        sem, lang = parsed
        if lang not in groups:
            groups[lang] = {}
        groups[lang][sem] = cls.credits

    # 找第一個有效配對
    for lang, sems in groups.items():
        if "一" in sems and "二" in sems:
            return ForeignPairStatus(
                language=lang,
                has_first_sem=True,
                has_second_sem=True,
                valid=True,
                credits=sems["一"] + sems["二"],
            )

    # 無有效配對：回傳學分最多的語種作為候選（方便前端顯示進度）
    if not groups:
        return ForeignPairStatus(
            language=None, has_first_sem=False, has_second_sem=False, valid=False, credits=0
        )
    best = max(groups, key=lambda l: sum(groups[l].values()))
    return ForeignPairStatus(
        language=best,
        has_first_sem="一" in groups[best],
        has_second_sem="二" in groups[best],
        valid=False,
        credits=0,
    )


def tally_credits(
    selections: Iterable[SelectedClass],
    student: Student,
    department: Department,
) -> tuple[dict[str, int], set, int, ForeignPairStatus]:
    """Walk a student's passed selections and bucket their credits.

    免修英文者（eng_passed = True）的大學外文課程不直接計入 english，
    而是在迴圈結束後透過 _validate_foreign_pair 驗證「同語種（一）＋（二）」
    配對，只有有效配對的學分才計入。

    Returns ``(credits, core_categories, pe_courses, foreign_pair_status)``.
    """
    credits = _empty_credits()
    core_categories: set[str] = set()
    pe_courses = 0
    foreign_classes: list[Class] = []

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
            # 先收集，迴圈後驗證配對
            foreign_classes.append(class_)
            continue
        else:
            bucket = category

        credits[bucket] += class_.credits
        if class_.core and bucket in _CORE_GE_BUCKETS:
            core_categories.add(bucket)

    # 驗證外文配對並計入 english
    foreign_pair = _validate_foreign_pair(foreign_classes)
    credits[ENGLISH] += foreign_pair.credits

    return credits, core_categories, pe_courses, foreign_pair


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
    core_categories: set[str],
    pe_courses: int,
    department: Department,
    foreign_pair: ForeignPairStatus,
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

    earned_core = len(core_categories)
    core_ge_status = CoreGEStatus(
        earned_categories=earned_core,
        required_categories=CORE_GE_REQUIRED,
        earned_category_list=sorted(core_categories),
        met=earned_core >= CORE_GE_REQUIRED,
        shortfall=max(CORE_GE_REQUIRED - earned_core, 0),
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
        "core_ge": asdict(core_ge_status),
        "foreign_pair": asdict(foreign_pair),
        "pe": asdict(pe_status),
        "total_excluding_pe": asdict(total_status),
        "graduation_ready": (
            all(s.met for s in categories.values())
            and core_ge_status.met
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
    credits, core_categories, pe_courses, foreign_pair = tally_credits(selections, student, department)
    result = evaluate(credits, core_categories, pe_courses, department, foreign_pair)
    result["student_id"] = student.id
    result["main_department_id"] = department.id
    return result


""" output example:
{
  "categories": {
    "humanities": {
      "earned": 5,      # 修了多少學分的課 (不考慮上限)
      "counted": 5,     # 實際算了多少學分
      "required": 3,    # 此類別需要多少學分
      "maximum": null,  # 此類別的學分上限 (null 則無上限)
      "met": true,      # 是否達標 (earned >= required)
      "shortfall": 0    # 距離達標還差多少學分 (如果已達標則為0)
    },
    "social": {
      "earned": 2,
      "counted": 2,
      "required": 3,
      "maximum": 7,
      "met": false,
      "shortfall": 1
    },
    "sciences": {
      "earned": 3,
      "counted": 3,
      "required": 3,
      "maximum": 7,
      "met": true,
      "shortfall": 0
    },
    "computer": {
      "earned": 0,
      "counted": 0,
      "required": 2,
      "maximum": 3,
      "met": false,
      "shortfall": 2
    },
    "residential": {
      "earned": 0,
      "counted": 0,
      "required": 0,
      "maximum": 3,
      "met": true,
      "shortfall": 0
    },
    "chinese": {
      "earned": 3,
      "counted": 3,
      "required": 3,
      "maximum": 6,
      "met": true,
      "shortfall": 0
    },
    "english": {
      "earned": 6,
      "counted": 6,
      "required": 6,
      "maximum": null,
      "met": true,
      "shortfall": 0
    }
  },
  "core_ge": {
    "earned_categories": 1,             # 修了幾個核通類別
    "required_categories": 2,           # 需要修幾個核通類別
    "earned_category_list": ["social"], # 修了哪些核通類別
    "met": false,                       # 是否達標 (earned >= required)
    "shortfall": 1                      # 差多少達標
  },
  "foreign_pair": {                     # 僅對 免修英文的人 有意義
    "language": "日文",                 # 目前修最多堂的語言 (沒有的話 null)
    "has_first_sem": true,              # 是否有大學外文（一）
    "has_second_sem": true,             # 是否有大學外文（二）
    "valid": true,                      # 外文（一）、（二）皆有且同語言才有效
    "credits": 6                        # 計入 english 的學分
  },
  "pe": {
    "earned_courses": 1,
    "required_courses": 4,
    "met": false,
    "shortfall": 3
  },
  "total_excluding_pe": {
    "earned": 19,
    "counted": 19,
    "required": 28,
    "maximum": null,
    "met": false,
    "shortfall": 9
  },
  "graduation_ready": false,
  "student_id": 1,
  "main_department_id": 2
}

"""
