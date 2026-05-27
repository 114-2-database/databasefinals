import hashlib

from app.db.session import SessionLocal
from app.models import Class, Department, SelectedClass, Student


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_create_department(db, name: str = "General Studies") -> Department:
    department = db.query(Department).filter(Department.name == name).first()
    if department:
        return department

    department = Department(
        name=name,
        humanities=0,
        social_min=0,
        social_max=0,
        sciences_min=0,
        sciences_max=0,
        computer_min=0,
        computer_max=0,
        residential_min=0,
        residential_max=0,
        chinese_min=0,
        chinese_max=0,
        pe=0,
        foreign=0,
    )
    db.add(department)
    db.commit()
    db.refresh(department)
    return department


def get_or_create_student(
    db,
    email: str,
    password: str,
    name: str,
    sex: str,
    department: Department,
) -> tuple[Student, bool]:
    student = db.query(Student).filter(Student.email == email).first()
    if student:
        return student, False

    student = Student(
        name=name,
        email=email,
        hashed_password=hash_password(password),
        sex=sex,
        main_department_id=department.id,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student, True


def get_or_create_class(
    db,
    name: str,
    credits: int,
    required_or_elective: str,
    teacher: str,
    core: bool,
    semester: str,
    remark: str = "",
) -> Class:
    class_ = (
        db.query(Class)
        .filter(Class.name == name, Class.academicYearSemester == semester)
        .first()
    )
    if class_:
        return class_

    class_ = Class(
        name=name,
        credits=credits,
        requiredOrElectiveCourse=required_or_elective,
        remark=remark,
        teacher=teacher,
        core=core,
        academicYearSemester=semester,
    )
    db.add(class_)
    db.commit()
    db.refresh(class_)
    return class_


def get_or_create_selected_class(
    db,
    student_id: int,
    class_id: int,
    ispassed: bool,
    score: float,
) -> SelectedClass:
    selected = (
        db.query(SelectedClass)
        .filter(
            SelectedClass.studentid == student_id,
            SelectedClass.classid == class_id,
        )
        .first()
    )
    if selected:
        return selected

    selected = SelectedClass(
        classid=class_id,
        studentid=student_id,
        ispassed=ispassed,
        score=score,
    )
    db.add(selected)
    db.commit()
    db.refresh(selected)
    return selected


def clear_tables(db) -> None:
    db.query(SelectedClass).delete(synchronize_session=False)
    db.query(Class).delete(synchronize_session=False)
    db.query(Student).delete(synchronize_session=False)
    db.query(Department).delete(synchronize_session=False)
    db.commit()


def seed() -> None:
    db = SessionLocal()
    try:
        clear_tables(db)
        department = get_or_create_department(db)
        student, created = get_or_create_student(
            db,
            email="demo@nccu.edu",
            password="demo1234",
            name="Demo Student",
            sex="M",
            department=department,
        )
        status = "created" if created else "exists"
        print(f"Seed student {status}: {student.email}")

        classes = [
            {
                "name": "General Education: Humanities",
                "credits": 2,
                "required_or_elective": "GE",
                "teacher": "Prof. Lin",
                "core": True,
                "semester": "2023-1",
                "remark": "HUM",
                "ispassed": True,
                "score": 86.0,
            },
            {
                "name": "General Education: Social",
                "credits": 2,
                "required_or_elective": "GE",
                "teacher": "Prof. Chen",
                "core": True,
                "semester": "2023-2",
                "remark": "SOC",
                "ispassed": True,
                "score": 90.0,
            },
            {
                "name": "General Education: Natural",
                "credits": 2,
                "required_or_elective": "GE",
                "teacher": "Prof. Wang",
                "core": False,
                "semester": "2024-1",
                "remark": "NAT",
                "ispassed": False,
                "score": 0.0,
            },
            {
                "name": "Information Literacy",
                "credits": 2,
                "required_or_elective": "GE",
                "teacher": "Prof. Wu",
                "core": False,
                "semester": "2024-1",
                "remark": "INFO",
                "ispassed": True,
                "score": 88.0,
            },
            {
                "name": "English for Academic Purposes",
                "credits": 3,
                "required_or_elective": "GE",
                "teacher": "Prof. Huang",
                "core": False,
                "semester": "2024-2",
                "remark": "ENG",
                "ispassed": True,
                "score": 84.0,
            },
            {
                "name": "Physical Education: Fitness",
                "credits": 1,
                "required_or_elective": "PE",
                "teacher": "Coach Lee",
                "core": False,
                "semester": "2023-1",
                "remark": "PE",
                "ispassed": True,
                "score": 92.0,
            },
        ]

        for entry in classes:
            class_ = get_or_create_class(
                db,
                name=entry["name"],
                credits=entry["credits"],
                required_or_elective=entry["required_or_elective"],
                teacher=entry["teacher"],
                core=entry["core"],
                semester=entry["semester"],
                remark=entry["remark"],
            )
            get_or_create_selected_class(
                db,
                student_id=student.id,
                class_id=class_.id,
                ispassed=entry["ispassed"],
                score=entry["score"],
            )
    finally:
        db.close()


if __name__ == "__main__":
    seed()
