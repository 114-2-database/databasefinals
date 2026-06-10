"""Student seed data generator for importing in main project.

How to use in your main project:
    from data.student_seed import seed_students
    from your_project.database import SessionLocal
    from your_project.students import Student

    with SessionLocal() as session:
        total = seed_students(session=session, student_model=Student)
        print(total)
"""

from __future__ import annotations

import hashlib
import random
import string
from pathlib import Path
from typing import Any

from data.department_seed import DEPARTMENT_BASE_DATA

TARGET_STUDENT_COUNT: int = 2000
RANDOM_SEED: int = 20260609

_RNG = random.Random(RANDOM_SEED)

_YEARS: tuple[int, ...] = (111, 112, 113, 114)
_YEAR_WEIGHTS: tuple[float, ...] = (0.22, 0.26, 0.30, 0.22)

_FOREIGN_LANGUAGE_DEPARTMENT_IDS: set[int] = {501, 502, 504, 506, 507, 508, 509}
_ENGLISH_DEPARTMENT_ID: int = 501

_SURNAMES: tuple[str, ...] = (
    "陳",
    "林",
    "黃",
    "張",
    "李",
    "王",
    "吳",
    "劉",
    "蔡",
    "楊",
    "許",
    "鄭",
    "謝",
    "郭",
    "洪",
    "邱",
    "曾",
    "廖",
    "賴",
    "徐",
    "周",
    "葉",
    "蘇",
    "莊",
)
_GIVEN_NAME_CHARS: tuple[str, ...] = tuple(
    "家宇承翰子宸柏丞哲睿彥廷恩庭安昕妤芯雅晴婷璇怡潔雯詠喬佳穎嘉欣"
    "思涵佩君于瑄書豪品妍語彤冠廷偉翔宏毅彥霖俊傑志豪宜蓁映彤以晴"
)


def _random_password(length: int = 12) -> str:
    """Generate a random password string.

    Args:
        length: Password length.

    Returns:
        Random password including letters and digits.
    """
    alphabet: str = string.ascii_letters + string.digits
    return "".join(_RNG.choice(alphabet) for _ in range(length))


def _hash_password(raw_password: str) -> str:
    """Hash password for storage.

    Args:
        raw_password: Raw password text.

    Returns:
        SHA-256 hex digest string.
    """
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


def _random_name() -> str:
    """Generate a realistic Chinese name.

    Returns:
        Full name with one surname and two given-name characters.
    """
    surname: str = _RNG.choice(_SURNAMES)
    given_name: str = "".join(_RNG.choice(_GIVEN_NAME_CHARS) for _ in range(2))
    return f"{surname}{given_name}"


def _eng_pass_probability(main_department_id: int, admission_year: int) -> float:
    """Estimate English exemption probability by major and admission year.

    Args:
        main_department_id: Student main department id.
        admission_year: Admission year prefix in student id.

    Returns:
        Probability between 0 and 1.
    """
    base_probability: float = 0.20

    if main_department_id in _FOREIGN_LANGUAGE_DEPARTMENT_IDS:
        base_probability = 0.48
    elif main_department_id in {301, 302, 401, 402, 403, 404}:
        base_probability = 0.30
    elif main_department_id in {701, 703}:
        base_probability = 0.25

    # Newer cohorts usually have slightly less time/opportunity to complete exemptions.
    if admission_year == 114:
        base_probability -= 0.05
    elif admission_year == 111:
        base_probability += 0.04

    if main_department_id == _ENGLISH_DEPARTMENT_ID:
        base_probability = max(base_probability, 0.65)

    return max(0.05, min(0.85, base_probability))


def _college_code(department_id: int) -> int:
    """Get college code from department id.

    Args:
        department_id: Department id.

    Returns:
        First digit college code.
    """
    return department_id // 100


def _pick_department_candidate(candidates: list[int], main_department_id: int) -> int | None:
    """Pick a department candidate with lower same-college probability.

    Args:
        candidates: Available candidate department ids.
        main_department_id: Main major department id.

    Returns:
        Selected department id or None if no candidate exists.
    """
    if not candidates:
        return None

    main_college_code: int = _college_code(main_department_id)
    same_college: list[int] = [department_id for department_id in candidates if _college_code(department_id) == main_college_code]
    different_college: list[int] = [
        department_id for department_id in candidates if _college_code(department_id) != main_college_code
    ]

    # Prefer different colleges to mimic realistic selection behavior.
    prefer_different_probability: float = 0.78
    if different_college and (not same_college or _RNG.random() < prefer_different_probability):
        picked: int = _RNG.choice(different_college)
    else:
        picked = _RNG.choice(same_college if same_college else candidates)

    candidates.remove(picked)
    return picked


def _pick_secondary_departments(main_department_id: int, admission_year: int) -> tuple[int | None, int | None, int | None]:
    """Pick optional double-major and minors.

    Args:
        main_department_id: Main major department id.
        admission_year: Admission year.

    Returns:
        Tuple of (sec_main_department_id, sub_main1_department_id, sub_main2_department_id).
    """
    if admission_year == 114:
        return None, None, None

    all_department_ids: list[int] = [department_id for department_id, _ in DEPARTMENT_BASE_DATA]
    candidates: list[int] = [department_id for department_id in all_department_ids if department_id != main_department_id]

    sec_main_department_id: int | None = None
    sub_main1_department_id: int | None = None
    sub_main2_department_id: int | None = None

    profile: str = _RNG.choices(
        population=("none", "sec_only", "minor1_only", "minor2_only", "sec_plus_minor1"),
        weights=(0.55, 0.17, 0.24, 0.03, 0.01),
        k=1,
    )[0]

    if profile in {"sec_only", "sec_plus_minor1"}:
        sec_main_department_id = _pick_department_candidate(
            candidates=candidates,
            main_department_id=main_department_id,
        )

    if profile in {"minor1_only", "sec_plus_minor1"}:
        sub_main1_department_id = _pick_department_candidate(
            candidates=candidates,
            main_department_id=main_department_id,
        )
    elif profile == "minor2_only":
        sub_main1_department_id = _pick_department_candidate(
            candidates=candidates,
            main_department_id=main_department_id,
        )
        sub_main2_department_id = _pick_department_candidate(
            candidates=candidates,
            main_department_id=main_department_id,
        )

    return sec_main_department_id, sub_main1_department_id, sub_main2_department_id


def _generate_student_rows(total_count: int) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    """Generate random student rows.

    Args:
        total_count: Number of rows to generate.

    Returns:
        Tuple of student seed rows and email/raw-password rows.
    """
    rows: list[dict[str, Any]] = []
    credential_rows: list[dict[str, str]] = []
    used_student_ids: set[int] = set()
    all_department_ids: list[int] = [department_id for department_id, _ in DEPARTMENT_BASE_DATA]

    # Guarantee coverage: every department has students from every admission year.
    for main_department_id in all_department_ids:
        for admission_year in _YEARS:
            if len(rows) >= total_count:
                break

            student_id: int
            while True:
                student_id_prefix: int = admission_year * 10**6 + main_department_id * 10**3
                random_suffix: int = _RNG.randint(0, 999)
                student_id = student_id_prefix + random_suffix
                if student_id not in used_student_ids:
                    break

            used_student_ids.add(student_id)
            sec_main_department_id, sub_main1_department_id, sub_main2_department_id = _pick_secondary_departments(
                main_department_id=main_department_id,
                admission_year=admission_year,
            )
            raw_password: str = _random_password()
            hashed_password: str = _hash_password(raw_password)
            eng_pass_probability: float = _eng_pass_probability(
                main_department_id=main_department_id,
                admission_year=admission_year,
            )
            eng_passed: bool = _RNG.random() < eng_pass_probability

            row: dict[str, Any] = {
                "id": student_id,
                "name": _random_name(),
                "email": f"{student_id}@nccu.edu.tw",
                "hashed_password": hashed_password,
                "sex": _RNG.choice(("男", "女")),
                "eng_passed": eng_passed,
                "main_department_id": main_department_id,
                "sec_main_department_id": sec_main_department_id,
                "sub_main1_department_id": sub_main1_department_id,
                "sub_main2_department_id": sub_main2_department_id,
            }
            rows.append(row)
            credential_rows.append(
                {
                    "email": row["email"],
                    "raw_password": raw_password,
                }
            )

    while len(rows) < total_count:
        admission_year: int = _RNG.choices(_YEARS, weights=_YEAR_WEIGHTS, k=1)[0]
        main_department_id: int = _RNG.choice(all_department_ids)

        student_id_prefix: int = admission_year * 10**6 + main_department_id * 10**3
        random_suffix: int = _RNG.randint(0, 999)
        student_id: int = student_id_prefix + random_suffix
        if student_id in used_student_ids:
            continue

        used_student_ids.add(student_id)

        sec_main_department_id, sub_main1_department_id, sub_main2_department_id = _pick_secondary_departments(
            main_department_id=main_department_id,
            admission_year=admission_year,
        )

        raw_password: str = _random_password()
        hashed_password: str = _hash_password(raw_password)
        eng_pass_probability: float = _eng_pass_probability(
            main_department_id=main_department_id,
            admission_year=admission_year,
        )
        eng_passed: bool = _RNG.random() < eng_pass_probability

        row: dict[str, Any] = {
            "id": student_id,
            "name": _random_name(),
            "email": f"{student_id}@nccu.edu.tw",
            "hashed_password": hashed_password,
            "sex": _RNG.choice(("男", "女")),
            "eng_passed": eng_passed,
            "main_department_id": main_department_id,
            "sec_main_department_id": sec_main_department_id,
            "sub_main1_department_id": sub_main1_department_id,
            "sub_main2_department_id": sub_main2_department_id,
        }
        rows.append(row)
        credential_rows.append(
            {
                "email": row["email"],
                "raw_password": raw_password,
            }
        )

    return rows, credential_rows


SEED_STUDENTS: list[dict[str, Any]]
SEED_STUDENT_CREDENTIALS: list[dict[str, str]]
SEED_STUDENTS, SEED_STUDENT_CREDENTIALS = _generate_student_rows(total_count=TARGET_STUDENT_COUNT)


def seed_students(
    session: Any,
    student_model: type[Any],
    credential_output_path: str = "data/student_seed_credentials.csv",
) -> int:
    """Upsert generated students into database.

    Args:
        session: SQLAlchemy session instance.
        student_model: ORM model class (e.g., `Student`).
        credential_output_path: Output path for credential CSV.

    Returns:
        Number of processed rows.
    """
    processed: int = 0
    for row in SEED_STUDENTS:
        existing: Any | None = session.get(student_model, row["id"])
        if existing is None:
            session.add(student_model(**row))
        else:
            existing.name = row["name"]
            existing.email = row["email"]
            existing.hashed_password = row["hashed_password"]
            existing.sex = row["sex"]
            existing.eng_passed = row["eng_passed"]
            existing.main_department_id = row["main_department_id"]
            existing.sec_main_department_id = row["sec_main_department_id"]
            existing.sub_main1_department_id = row["sub_main1_department_id"]
            existing.sub_main2_department_id = row["sub_main2_department_id"]
        processed += 1

    session.commit()
    export_seed_credentials_to_csv(output_path=credential_output_path)
    return processed


def export_seed_students_to_csv(output_path: str = "data/student_seed_preview.csv") -> str:
    """Export generated student seed data to CSV for preview.

    Args:
        output_path: Output CSV path.

    Returns:
        Absolute path string of the generated CSV file.

    Raises:
        ImportError: If pandas is not installed.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "pandas is required for CSV export. Install it with `pip install pandas`."
        ) from exc

    columns: list[str] = [
        "id",
        "name",
        "email",
        "hashed_password",
        "sex",
        "eng_passed",
        "main_department_id",
        "sec_main_department_id",
        "sub_main1_department_id",
        "sub_main2_department_id",
    ]
    frame = pd.DataFrame(SEED_STUDENTS, columns=columns)
    nullable_int_columns: tuple[str, ...] = (
        "sec_main_department_id",
        "sub_main1_department_id",
        "sub_main2_department_id",
    )
    for column in nullable_int_columns:
        frame[column] = frame[column].astype("Int64")

    target_path: Path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target_path, index=False, encoding="utf-8-sig")
    return str(target_path.resolve())


def export_seed_credentials_to_csv(output_path: str = "data/student_seed_credentials.csv") -> str:
    """Export generated testing credentials to CSV.

    Args:
        output_path: Output CSV path.

    Returns:
        Absolute path string of generated credential CSV.

    Raises:
        ImportError: If pandas is not installed.
    """
    try:
        import pandas as pd
    except ImportError as exc:
        raise ImportError(
            "pandas is required for CSV export. Install it with `pip install pandas`."
        ) from exc

    frame = pd.DataFrame(SEED_STUDENT_CREDENTIALS, columns=["email", "raw_password"])
    target_path: Path = Path(output_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(target_path, index=False, encoding="utf-8-sig")
    return str(target_path.resolve())


def export_seed_preview_files(
    student_output_path: str = "data/student_seed_preview.csv",
    credential_output_path: str = "data/student_seed_credentials.csv",
) -> dict[str, str]:
    """Export both student seed CSV and test-credential CSV.

    Args:
        student_output_path: Output path for student preview CSV.
        credential_output_path: Output path for credential CSV.

    Returns:
        Mapping with generated absolute paths.
    """
    student_csv_path: str = export_seed_students_to_csv(output_path=student_output_path)
    credential_csv_path: str = export_seed_credentials_to_csv(output_path=credential_output_path)
    return {
        "student_csv_path": student_csv_path,
        "credential_csv_path": credential_csv_path,
    }
