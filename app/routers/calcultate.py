from app.core.algorthms import calculate_score
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session  
from app.db.session import SessionLocal

router = APIRouter()

@router.get("/calculate")
async def calculate(request: Request, db: Session = Depends(SessionLocal)):
    student_id = request.session.get("student_id")
    if not student_id:
        return {"error": "User not logged in"}

    score = calculate_score(db, student_id)
    return {"score": score}