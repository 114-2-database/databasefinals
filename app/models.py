from sqlalchemy import Column, Integer, BigInteger, String, Text, DateTime, Boolean, ForeignKey, DECIMAL, Date
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
import uuid
import bcrypt
import secrets
import re
import hashlib
import json
from datetime import datetime
    
class Department(Base):
    __tablename__ = "departments"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), unique=True, nullable=False, index=True)
    humanities_min = Column(Integer, nullable=False)
    humanities_max = Column(Integer, nullable=True)
    social_min = Column(Integer, nullable=False)
    social_max = Column(Integer, nullable=True)
    sciences_min = Column(Integer, nullable=False)
    sciences_max = Column(Integer, nullable=True)
    computer_min = Column(Integer, nullable=False)
    computer_max = Column(Integer, nullable=False)
    residential_min = Column(Integer, nullable=False)
    residential_max = Column(Integer, nullable=True)
    chinese_min = Column(Integer, nullable=False)
    chinese_max = Column(Integer, nullable=True)
    pe = Column(Integer, nullable=False)
    foreign = Column(Integer, nullable=False)


class Student(Base):
    __tablename__ = "students"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    sex = Column(String(5), nullable=False)
    eng_passed = Column(Boolean, default=False)
    main_department_id = Column(Integer, ForeignKey('departments.id'), nullable=False, index=True)
    sec_main_department_id = Column(Integer, ForeignKey('departments.id'), index=True)
    sub_main1_department_id = Column(Integer, ForeignKey('departments.id'), index=True)
    sub_main2_department_id = Column(Integer, ForeignKey('departments.id'), index=True)
    
    # Use main_department_id as the primary department link.
    main_department = relationship("Department", foreign_keys=[main_department_id])
    secondary_department = relationship("Department", foreign_keys=[sec_main_department_id])
    sub_main1_department = relationship("Department", foreign_keys=[sub_main1_department_id])
    sub_main2_department = relationship("Department", foreign_keys=[sub_main2_department_id])

class Class(Base):
    __tablename__ = "classes"
    
    id = Column(BigInteger, primary_key=True, index=True)
    name = Column(String(64), nullable=False, index=True)
    credits = Column(Integer, nullable=False)
    requiredOrElectiveCourse = Column(String(64), nullable=False, index=True)
    remark = Column(String(64))
    teacher = Column(String(64), nullable=False, index=True)
    core = Column(Boolean, nullable=False)
    academicYearSemester = Column(String(32), index=True)

class SelectedClass(Base):
    __tablename__ = "selected_classes"
    
    classid = Column(BigInteger, ForeignKey('classes.id'), primary_key=True, index=True)
    studentid = Column(Integer, ForeignKey('students.id'), primary_key=True, index=True)
    ispassed = Column(Boolean, default=False)
    score = Column(DECIMAL(10, 2), default=0.00)
    
    class_ = relationship("Class", backref="selected_classes")
    student = relationship("Student", backref="selected_classes")
