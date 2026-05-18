from pydantic import BaseModel


class LoginForm(BaseModel):
    student_no: str
    password: str
