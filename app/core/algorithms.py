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
    
    - 英外文課程的 remark 都是「外文通識」，改用「課名」區分大學英文 / 大學外文 / 選修英文
      (含「大學英文」→英文；含「大學外文」或「選修英文」→外文)

    - 英文免修者需擇一補修：①兩堂不同的選修英文共 6 學分；②同語種大學外文（一）＋（二）。
      兩案皆未達成則不通過，但已修學分仍計入 english（例如只修一堂選修英文計 3 學分）

    - ER-Diagram 裡面用 collegeEnglishExemption 來表示大學英文免修，但在 model 裡面用 eng_passed 來表示，所以這邊暫時用 eng_passed
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
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


# remark 文字 → 標準類別代號的對照表。比對前會去除空白並轉小寫，因此同一寫法只需列一次。
# 也收錄類別代號本身（如 "social"），讓 ``chosen_category`` 填 "social" 時能與「社會通」一致解析。
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
    # 資訊通識 — 同時涵蓋純資訊與跨領域寫法；跨領域與否改由 remark 列出幾個類別來判斷，
    # 不再需要獨立的 COMPUTER_CROSS 代號。
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


# remark 內分隔符：中文「、」「，」、半形「,」「/」、半形/全形括號，以及多個空白。
# 把括號也視為分隔符，是為了支援「跨領域(人文、社會)」「跨領域（人文、社會）」這類寫法
# ——拆出 "跨領域"、"人文"、"社會"，其中 "跨領域" 無法對應類別會被自動忽略，
# 只留下實際的領域類別（全形「（）」與半形「()」皆可）。
_REMARK_SPLIT_RE = re.compile(r"[、，,/（）()]+|\s{2,}")

# 比對大學外文課程名稱，抓出學期和語種，例如 "大學外文（一）：日文" → ("一", "日文")
# 全形「（）」「：」與半形「()」「:」皆可，括號內外允許空白。
_FOREIGN_LANG_RE = re.compile(r"大學外文\s*[（(]\s*([一二])\s*[）)]\s*[：:]\s*(.+)")


def _normalize(text: str | None) -> str | None:
    if not text:
        return None
    return _REMARK_TO_CATEGORY.get(text.strip().lower())


def parse_categories(remark: str | None) -> list[str]:
    """把課程 remark 拆解成其列出的標準類別。

    一個 remark 最多可列三個類別，以「、」「，」等分隔（例如「社會通、人文通」）；
    也支援「跨領域(人文、社會)」這類含括號的寫法。無法辨識的詞會被略過，
    重複者保留先後順序去重。
    """
    if not remark:
        return []
    seen: list[str] = []
    for token in _REMARK_SPLIT_RE.split(remark):
        category = _normalize(token)
        if category and category not in seen:
            seen.append(category)
    return seen


def _foreign_category_from_name(name: str | None) -> str | None:
    """當 remark 無法判別時（如爬蟲統一標的「外文通識」），改用課名判斷英外文。

    * 課名含「大學英文」              → ENGLISH（大學英文）
    * 課名含「大學外文」或「選修英文」→ FOREIGN_ALT（免修英文可用的外文）
    * 其餘                            → None
    """
    if not name:
        return None
    if "大學英文" in name:
        return ENGLISH
    if "大學外文" in name or "選修英文" in name:
        return FOREIGN_ALT
    return None


def categorize_selection(
    class_: Class | None, selected: SelectedClass | None
) -> str | None:
    """判斷這筆選課的學分應計入哪個通識類別。

    判斷順序：
    1. 若 ``SelectedClass.chosen_category`` 有設定且在 remark 列出的類別中，採用之。
    2. 否則採用 remark 第一個列出的類別，避免學生尚未選時學分被忽略。
    3. 若 remark 無法對應任何類別（例如「外文通識」），改用課名判斷英/外文。
    4. 都無法判別則回傳 ``None``。
    """
    options = parse_categories(class_.remark) if class_ else []
    if not options:
        # remark 判不出來 → 退而用課名辨識大學英文 / 大學外文 / 選修英文
        return _foreign_category_from_name(getattr(class_, "name", None)) if class_ else None

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
    # 本身課程已涵蓋資訊的科系（統計、資管、應數、資科、地政測資組…）
    # 以 ``computer_max = 0`` 標記，代表其學生的資訊通識學分不計入。
    return department is not None and department.computer_max == 0


def is_exempt_from_english(student: Student) -> bool:
    return bool(student.eng_passed)


# --- Database lookups --------------------------------------------------------

def get_student(db: Session, student_id: int) -> Student | None:
    return db.query(Student).filter(Student.id == student_id).first()


def get_passed_selections(db: Session, student_id: int) -> list[SelectedClass]:
    """取出該生所有「已通過」的 SelectedClass，並一併 eager join 對應的 Class，
    讓呼叫端能同時讀到課程資訊（學分、remark、core）與 chosen_category，避免 N+1 查詢。"""
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
    counted: int        # earned 受 ``maximum`` 上限後的實際計入學分
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
    # 學生在幾個不同的通識領域（人文/社會/自然）至少通過一門核心通識課。
    earned_categories: int
    required_categories: int
    earned_category_list: list   # 已涵蓋的類別代號
    met: bool
    shortfall: int


@dataclass
class ForeignPairStatus:
    # 免修大學英文者的補修狀態，需擇一達成（僅在 student.eng_passed = True 時有意義）：
    #   方案一 selective_english：兩堂不同的選修英文共 6 學分
    #   方案二 foreign_pair：同語種大學外文（一）＋（二）
    language: str | None        # 大學外文配對的語種（如 "日文"）；選修英文方案或無配對則為 None
    has_first_sem: bool         # 是否有大學外文（一）
    has_second_sem: bool        # 是否有大學外文（二）
    valid: bool                 # 是否有任一方案達成
    credits: int                # 計入 english bucket 的學分（未達標時為「部分學分」）
    plan: str | None = None     # 達成的方案："selective_english" / "foreign_pair" / None
    # 實際計入學分的課程名稱（顯示用）。例如部分達成時，可讓前端列出已修的外文/選修英文課
    courses: list[str] = field(default_factory=list)


# 只有人文、社會、自然 三領域有核心通識課程。
_CORE_GE_BUCKETS: frozenset[str] = frozenset({HUMANITIES, SOCIAL, SCIENCES})

CORE_GE_REQUIRED = 2


def _empty_credits() -> dict[str, int]:
    return {
        HUMANITIES: 0, SOCIAL: 0, SCIENCES: 0, COMPUTER: 0,
        RESIDENTIAL: 0, CHINESE: 0, ENGLISH: 0,
    }


def _validate_foreign_pair(
    foreign_classes: list[Class], required_credits: int = 6
) -> ForeignPairStatus:
    """驗證免修英文的補修課程是否達成任一方案。

    傳入的是學生（已免修英文）修過的「大學外文 / 選修英文」課程：

    * 方案二 foreign_pair：同一語種同時有大學外文（一）和（二）→ 有效，計入該配對學分。
    * 方案一 selective_english：兩堂(以上)不同的選修英文且共 ``required_credits`` 學分 → 有效。
    * 兩案皆未達成：回傳「部分學分」——取學分最多的單一來源（同語種大學外文總和，
      或選修英文總和），不同語種之間不加總，``valid = False``。

    回傳的 ``credits`` 即為應計入 english bucket 的學分。
    """
    # 大學外文：{語種: {學期: 學分}} 與 {語種: {學期: 課名}}
    lang_groups: dict[str, dict[str, int]] = {}
    lang_names: dict[str, dict[str, str]] = {}
    # 選修英文：{課名: 學分}（不同課名才算不同課；同名只算一次）
    selective: dict[str, int] = {}

    for cls in foreign_classes:
        name = (cls.name or "").strip()
        if "選修英文" in name:
            selective[name] = cls.credits
            continue
        parsed = _parse_foreign_lang(name)
        if parsed:
            sem, lang = parsed
            lang_groups.setdefault(lang, {})[sem] = cls.credits
            lang_names.setdefault(lang, {})[sem] = name

    # 方案二：同語種大學外文（一）＋（二）
    for lang, sems in lang_groups.items():
        if "一" in sems and "二" in sems:
            return ForeignPairStatus(
                language=lang,
                has_first_sem=True,
                has_second_sem=True,
                valid=True,
                credits=sems["一"] + sems["二"],
                plan="foreign_pair",
                courses=[lang_names[lang]["一"], lang_names[lang]["二"]],
            )

    # 方案一：兩堂以上不同的選修英文，共達 required_credits 學分
    if len(selective) >= 2 and sum(selective.values()) >= required_credits:
        return ForeignPairStatus(
            language=None,
            has_first_sem=False,
            has_second_sem=False,
            valid=True,
            credits=sum(selective.values()),
            plan="selective_english",
            courses=list(selective),
        )

    # 皆未達標：取學分最多的單一來源作為「部分學分」
    best_credits = 0
    best_lang: str | None = None
    best_courses: list[str] = []
    for lang, sems in lang_groups.items():
        total = sum(sems.values())
        if total > best_credits:
            best_credits, best_lang = total, lang
            best_courses = list(lang_names[lang].values())
    sel_total = sum(selective.values())
    if sel_total > best_credits:
        best_credits, best_lang = sel_total, None
        best_courses = list(selective)

    if best_lang is not None:
        sems = lang_groups[best_lang]
        return ForeignPairStatus(
            language=best_lang,
            has_first_sem="一" in sems,
            has_second_sem="二" in sems,
            valid=False,
            credits=best_credits,
            plan=None,
            courses=best_courses,
        )
    return ForeignPairStatus(
        language=None,
        has_first_sem=False,
        has_second_sem=False,
        valid=False,
        credits=best_credits,
        plan=None,
        courses=best_courses,
    )


def tally_credits(
    selections: Iterable[SelectedClass],
    student: Student,
    department: Department,
) -> tuple[dict[str, int], set, int, ForeignPairStatus]:
    """走訪學生已通過的選課，將學分歸入各通識類別。

    免修英文者（eng_passed = True）的大學外文 / 選修英文課程不直接計入 english，
    而是先收集，迴圈結束後透過 _validate_foreign_pair 依「免修補修雙方案」驗證，
    再把應計學分（達標 6 學分，或未達標的部分學分）加入 english。

    回傳 ``(credits, core_categories, pe_courses, foreign_pair_status)``。
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

    # 依免修補修雙方案驗證外文/選修英文，並把應計學分加入 english
    foreign_pair = _validate_foreign_pair(foreign_classes, department.foreign)
    credits[ENGLISH] += foreign_pair.credits

    return credits, core_categories, pe_courses, foreign_pair


# --- Requirement evaluation --------------------------------------------------

# 全校最低畢業學分門檻（不含體育）。
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
    """將彙總後的學分與該科系的畢業門檻逐項比對。"""
    categories: dict[str, CategoryStatus] = {
        # 人文通識現有 min/max（max 可為 null 代表無上限）；
        # foreign（大學英文門檻）仍為單一整數，視為最低要求、無上限。
        HUMANITIES: _status(
            credits[HUMANITIES], department.humanities_min, department.humanities_max
        ),
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

    # 不含體育的總學分：各類別「受上限後」的學分加總，避免某類別超修
    # 來掩蓋另一類別的不足。
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
    """計算 ``student_id`` 的畢業審核資訊。

    回傳可序列化為 JSON 的字典，包含各類別學分、各項是否達標、體育門數，以及總學分。
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
    "language": "日文",                 # 大學外文配對的語種 (選修英文方案或無配對則為 null)
    "has_first_sem": true,              # 是否有大學外文（一）
    "has_second_sem": true,             # 是否有大學外文（二）
    "valid": true,                      # 是否達成任一補修方案
    "credits": 6,                       # 計入 english 的學分 (未達標時為部分學分)
    "plan": "foreign_pair",             # 達成方案: "foreign_pair"/"selective_english"/null
    "courses": ["大學外文（一）：日文", "大學外文（二）：日文"]  # 計入學分的課程 (顯示用)
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
