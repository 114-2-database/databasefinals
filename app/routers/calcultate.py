from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.core.algorithms import calculate_score
from app.db.session import SessionLocal

router = APIRouter()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/calculate")
async def calculate(request: Request, db: Session = Depends(get_db)):
    student_id = request.session.get("student_id")
    if not student_id:
        return {"error": "User not logged in"}

    score = calculate_score(db, student_id)
    return {"score": score}