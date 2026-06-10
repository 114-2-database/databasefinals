from pydantic import BaseModel


class LoginForm(BaseModel):
    student_no: str
    password: str

class DetailType(BaseModel):
    type_: str