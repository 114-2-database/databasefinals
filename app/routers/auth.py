import hashlib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Student, Class, SelectedClass
from app.schemas import LoginForm, DetailType
from app.core.jwt import create_access_token
from app.core.deps import verify_token
from app.core.algorithms import calculate_score

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def hash_password(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# @router.get("/login")
# async def login_page(request: Request):
#     return request.app.state.templates.TemplateResponse(
#         "login.html", {"request": request, "error": None}
#     )


# @router.post("/login")
# async def login_submit(
#     request: Request,
#     student_no: str = Form(...),
#     password: str = Form(...),
#     db: Session = Depends(get_db),
# ):
#     hashed = hash_password(password)
#     student = (
#         db.query(Student)
#         .filter(Student.email == student_no, Student.hashed_password == hashed)
#         .first()
#     )
#     if not student:
#         return request.app.state.templates.TemplateResponse(
#             "login.html", {"request": request, "error": "帳號或密碼錯誤"}
#         )
#     request.session["student_id"] = student.id
#     return RedirectResponse(url="/dashboard", status_code=303)


# @router.get("/logout")
# async def logout(request: Request):
#     request.session.clear()
#     return RedirectResponse(url="/login", status_code=303)


@router.post("/api/login")
def log_in(data: LoginForm, db: Session = Depends(get_db)):
    student = db.query(Student).filter(Student.id == data.student_no).first()
    hashed_password = hash_password(data.password)
    if not student or student.hashed_password != hashed_password:
        return {
            "StatusCode": 401,
            "Message":"帳號或密碼錯誤"
        }
    else:
        access_token = create_access_token(data={"student_id": student.id})
        return {
            "StatusCode": 200,
            "Message":"success",
            "Data":{
                "token": access_token,
                "student_number": student.id,
                "name": student.name
            }
        }
        
@router.get("/api/dashboard")
def dashboard(payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    payload_student_id = payload.get("student_id")
    
    result = calculate_score(db, payload_student_id) #引用algorthms的函式，並將結果存儲在 result 變量中
    
    student = db.query(Student).filter(Student.id == payload_student_id).first()
    student_info = {
        "name": student.name,
        "main_department": student.main_department.name,
        "secondary_department": student.secondary_department.name if student.secondary_department else None,
        "sub_main1_department": student.sub_main1_department.name if student.sub_main1_department else None,
        "sub_main2_department": student.sub_main2_department.name if student.sub_main2_department else None
    }
    
    general_education_graduation_credits = {
        "general_education_required_credits": result["total_excluding_pe"]["required"],
        "general_education_credits_taken": result["total_excluding_pe"]["counted"]
    }
    core_general_education = {
        "required_courses":result["core_ge"]["required_categories"],
        "taken_courses":result["core_ge"]["earned_categories"] 
    }
    humanities = {
        "humanities_maximum_credits":result["categories"]["humanities"]["maximum"],
        "humanities_required_credits":result["categories"]["humanities"]["required"],
        "humanities_credit_taken":result["categories"]["humanities"]["counted"]
    }
    social = {
        "social_maximum_credits":result["categories"]["social"]["maximum"],
        "social_required_credits":result["categories"]["social"]["required"],
        "social_credit_taken":result["categories"]["social"]["counted"]
    }
    sciences = {
        "sciences_maximum_credits":result["categories"]["sciences"]["maximum"],
        "sciences_required_credits":result["categories"]["sciences"]["required"],
        "sciences_credit_taken":result["categories"]["sciences"]["counted"]
    }
    computer = {
        "computer_maximum_credits":result["categories"]["computer"]["maximum"],
        "computer_required_credits":result["categories"]["computer"]["required"],
        "computer_credit_taken":result["categories"]["computer"]["counted"]
    }
    residential = {
        "residential_maximum_credits":result["categories"]["residential"]["maximum"],
        "residential_required_credits":result["categories"]["residential"]["required"],
        "residential_credit_taken": result["categories"]["residential"]["counted"]
    }
    foreign = {
        "foreign_maximum_credits":result["categories"]["english"]["maximum"],
        "foreign_required_credits":result["categories"]["english"]["required"],
        "foreign_credit_taken": result["categories"]["english"]["counted"]
    }
    chinese = {
        "chinese_maximum_credits":result["categories"]["chinese"]["maximum"],
        "chinese_required_credits":result["categories"]["chinese"]["required"],
        "chinese_credit_taken": result["categories"]["chinese"]["counted"]
    }
    pe = {
        "pe_maximum_credits":result["pe"]["required_courses"],
        "pe_required_credits":result["pe"]["required_courses"],
        "pe_credit_taken":result["pe"]["earned_courses"]
    }
    # TODO: 計算學生已修習的一般教育課程學分數，並更新 general_education_graduation_credits["General_Education_Taken"]
    
    return {
        "StatusCode": 200,
        "Message": "success",
        "Data": {
            "student_info": student_info,
            "general_education_graduation_credits": general_education_graduation_credits,
            "core_general_education": core_general_education,
            "humanities": humanities,
            "social": social,
            "sciences": sciences,
            "computer": computer,
            "residential": residential,
            "foreign": foreign,
            "chinese": chinese,
            "pe": pe
        }
    }
    
@router.post("/api/details")
def details(data: DetailType, payload: dict = Depends(verify_token), db: Session = Depends(get_db)):
    student_id = payload.get("student_id")
    # student = db.query(Student).filter(Student.id == student_id).first()
    query = (
        db.query(SelectedClass)
        .join(Class)
        .filter(SelectedClass.studentid == student_id)
    )
    if data.type != "all":
        query = query.filter(Class.remark == data.type)
        
    selected_class = query.all()
    selected_classes_info = []
    for sc in selected_class:
        selected_classes_info.append({
            "class_name": sc.class_.name,
            "credits": sc.class_.credits,
            "remark": sc.class_.remark,
            "core": sc.class_.core,
            "ispassed": sc.ispassed
        })

    return {
        "StatusCode": 200,
        "Message": "success",
        "Data": {
            "type": data.type,
            "selected_classes": selected_classes_info
        }
    }
    # if data.type == "all":
    #     selected_class = db.query(SelectedClass).filter(SelectedClass.studentid == student_id).all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "humanities":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "humanities").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "social":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "social").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "sciences":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "sciences").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "computer":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "computer").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "residential":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "residential").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "chinese":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "chinese").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "foreign":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "foreign").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    # elif data.type == "pe":
    #     selected_class = db.query(SelectedClass).join(Class).filter(SelectedClass.studentid == student_id, Class.remark == "pe").all()
    #     selected_classes_info = []
    #     for sc in selected_class:
    #         selected_classes_info.append({
    #             "class_name": sc.class_.name,
    #             "credits": sc.class_.credits,
    #             "remark": sc.class_.remark,
    #             "core": sc.class_.core,
    #             "ispassed": sc.ispassed
    #         })
    #     return {
    #         "StatusCode": 200,
    #         "Message": "success",
    #         "Data": {
    #             "type": data.type,
    #             "selected_classes": selected_classes_info
    #         }
    #     }
    #TODO: 根據 data.type 的值，返回對應的詳細資訊，例如已修習課程、成績等
    
    