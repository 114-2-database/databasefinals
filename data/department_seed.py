"""Department seed data for importing in main project."""

from __future__ import annotations

from typing import Any

DEFAULT_RULES: dict[str, int | None] = {
    "humanities_min": 3,
    "humanities_max": 7,
    "social_min": 3,
    "social_max": 7,
    "sciences_min": 3,
    "sciences_max": 7,
    "computer_min": 2,
    "computer_max": 3,
    "residential_min": 0,
    "residential_max": 3,
    "chinese_min": 3,
    "chinese_max": 6,
    "pe": 4,
    "foreign": 6,
}

# Departments exempt from information general education field.
EXEMPT_COMPUTER_IDS: set[int] = {304, 306, 701, 703}

DEPARTMENT_BASE_DATA: list[tuple[int, str]] = [
    (101, "中文系"),
    (102, "教育系"),
    (103, "歷史系"),
    (104, "哲學系"),
    (202, "政治系"),
    (203, "外交系"),
    (204, "社會系"),
    (205, "財政系"),
    (206, "公行系"),
    (207, "地政系"),
    (208, "經濟系"),
    (209, "民族系"),
    (301, "國貿系"),
    (302, "金融系"),
    (303, "會計系"),
    (304, "統計系"),
    (305, "企管系"),
    (306, "資管系"),
    (307, "財管系"),
    (308, "風管系"),
    (401, "新聞系"),
    (402, "廣告系"),
    (403, "廣電系"),
    (404, "傳播學程"),
    (501, "英文系"),
    (502, "阿語系"),
    (504, "斯語系"),
    (506, "日文系"),
    (507, "韓文系"),
    (508, "土語系"),
    (509, "歐語學程"),
    (601, "法律系"),
    (701, "應數系"),
    (702, "心理系"),
    (703, "資科系"),
]


def _build_department_row(department_id: int, name: str) -> dict[str, Any]:
    """Build one department seed row based on default rules.

    Args:
        department_id: Department id.
        name: Department name.

    Returns:
        Department row dict for ORM construction.
    """
    row: dict[str, Any] = {
        "id": department_id,
        "name": name,
        **DEFAULT_RULES,
    }

    if department_id in EXEMPT_COMPUTER_IDS:
        row["computer_min"] = 0
        row["computer_max"] = 0

    return row


SEED_DEPARTMENTS: list[dict[str, Any]] = [
    _build_department_row(department_id=department_id, name=name)
    for department_id, name in DEPARTMENT_BASE_DATA
]


def seed_departments(session: Any, department_model: type[Any]) -> int:
    """Upsert generated departments into database.

    Args:
        session: SQLAlchemy session instance.
        department_model: ORM model class (e.g., `Department`).

    Returns:
        Number of processed rows.
    """
    processed: int = 0
    for row in SEED_DEPARTMENTS:
        existing: Any | None = session.get(department_model, row["id"])
        if existing is None:
            session.add(department_model(**row))
        else:
            existing.name = row["name"]
            existing.humanities_min = row["humanities_min"]
            existing.humanities_max = row["humanities_max"]
            existing.social_min = row["social_min"]
            existing.social_max = row["social_max"]
            existing.sciences_min = row["sciences_min"]
            existing.sciences_max = row["sciences_max"]
            existing.computer_min = row["computer_min"]
            existing.computer_max = row["computer_max"]
            existing.residential_min = row["residential_min"]
            existing.residential_max = row["residential_max"]
            existing.chinese_min = row["chinese_min"]
            existing.chinese_max = row["chinese_max"]
            existing.pe = row["pe"]
            existing.foreign = row["foreign"]
        processed += 1

    session.commit()
    return processed
