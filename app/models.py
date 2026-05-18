from sqlalchemy import Boolean, Column, ForeignKey, Integer, String
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


class Student(Base):
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, index=True)
    student_no = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(50), nullable=False)
    password_hash = Column(String(64), nullable=False)

    items = relationship("StudentCheckItem", back_populates="student")


class CheckItem(Base):
    __tablename__ = "check_items"

    id = Column(Integer, primary_key=True, index=True)
    category = Column(String(10), nullable=False)  # GE or PE
    title = Column(String(100), nullable=False)

    students = relationship("StudentCheckItem", back_populates="item")


class StudentCheckItem(Base):
    __tablename__ = "student_check_items"

    id = Column(Integer, primary_key=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id"), nullable=False)
    item_id = Column(Integer, ForeignKey("check_items.id"), nullable=False)
    passed = Column(Boolean, default=False, nullable=False)

    student = relationship("Student", back_populates="items")
    item = relationship("CheckItem", back_populates="students")
