import hashlib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Student, Class, SelectedClass
from app.schemas import LoginForm, DetailType
from app.core.jwt import create_access_token
from app.core.deps import verify_token

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@router.get("/login")
async def login_page(request: Request):
    return request.app.state.templates.TemplateResponse(
        "login.html", {"request": request, "error": None}
    )


@router.post("/login")
async def login_submit(
    request: Request,
    student_no: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    hashed = hash_password(password)
    student = (
        db.query(Student)
        .filter(Student.email == student_no, Student.hashed_password == hashed)
        .first()
    )
    if not student:
        return request.app.state.templates.TemplateResponse(
            "login.html", {"request": request, "error": "帳號或密碼錯誤"}
        )
    request.session["student_id"] = student.id
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


@router.post("/api/login")
def log_in(data: LoginForm, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == data.student_no).first()
    hashed_passsword = hash_password(data.password)
    if not student or student.hashed_password != hashed_passsword:
        return {
            "StatusCode":"401",
            "Message":"帳號或密碼錯誤"
        }
    else:
        access_token = create_access_token(data={"student_id": student.id})
        return {
            "StatusCode":"200",
            "Message":"登入成功",
            "Data":{
                "Token": access_token,
                "StudentNumber": student.id,
                "Name": student.name
            }
        }
        
@router.get("/api/dashboard")
def dashboard(payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    payload_student_id = payload.get("student_id")
    student = db.query(Student).filter(Student.id == payload_student_id).first()
    student_info = {
        "Name": student.name,
        "main_department": student.main_department.name,
        "secondary_department": student.secondary_department.name if student.secondary_department else None,
        "sub_main1_department": student.sub_main1_department.name if student.sub_main1_department else None,
        "sub_main2_department": student.sub_main2_department.name if student.sub_main2_department else None
    }
    
    general_education_graduation_credits = {
        "General_Education_Credits": 28,
        "General_Education_Taken": 0
    }
    
    # TODO: 計算學生已修習的一般教育課程學分數，並更新 general_education_graduation_credits["General_Education_Taken"]
    
    return {
        "StatusCode": "200",
        "Message": "成功獲取學生資訊",
        "Data": {
            "StudentInfo": student_info,
            "GeneralEducationGraduationCredits": general_education_graduation_credits
        }
    }
    
@router.post("/api/details")
def details(data: DetailType, payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    student_id = payload.get("student_id")
    student = db.query(Student).filter(Student.id == student_id).first()
    if data.type == "all":
        pass
    elif data.type == "humanities":
        seclected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "humanities").all()
        selected_classes_info = []
        for sc in seclected_class:
            selected_classes_info.append({
                "class_name": sc.class_.name,
                "credits": sc.class_.credits,
                "remark": sc.class_.remark,
                "core": sc.class_.core,
                "Passed": sc.ispassed
            })
        return {
            "StatusCode": "200",
            "Message": "success",
            "Data": {
                "type": data.type,
                "SelectedClasses": selected_classes_info
            }
        }
    #TODO: 根據 data.type 的值，返回對應的詳細資訊，例如已修習課程、成績等
    
    