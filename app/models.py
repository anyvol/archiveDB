from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum
from sqlalchemy.orm import relationship
import enum
import datetime

Base = declarative_base()

class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    position = Column(String, nullable=True)
    department = Column(String, nullable=True)
    role = Column(Enum(UserRole), default=UserRole.user)

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    code = Column(String(8), unique=True, index=True, nullable=False)  # КО
    name = Column(String, nullable=False)
    department = Column(String, nullable=True)

class ClassCodeKD(Base):
    __tablename__ = "class_codes_kd"
    id = Column(Integer, primary_key=True)
    code = Column(String(6), unique=True, index=True, nullable=False)  # ККХ
    description = Column(String, nullable=True)

class ClassCodeTD(Base):
    __tablename__ = "class_codes_td"
    id = Column(Integer, primary_key=True)
    code = Column(String(7), unique=True, index=True, nullable=False)  # КХД (+ доп длина)
    description = Column(String, nullable=True)

class BaseDocument(Base):
    __tablename__ = "documents"
    id = Column(Integer, primary_key=True)
    file_path = Column(String, nullable=False)
    file_name = Column(String, unique=True, nullable=False)
    created_by = Column(String, nullable=True)  # автор создания
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=True)  # кто загрузил
    position = Column(String, nullable=True)
    uploaded_user = relationship("User")
    department = Column(String, nullable=True)
    type = Column(String, index=True)  # 'KD' или 'TD'
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    design_document = relationship("DesignDocument", back_populates="base_doc", uselist=False)
    tech_document = relationship("TechDocument", back_populates="base_doc", uselist=False)

class DesignDocument(Base):
    __tablename__ = "design_documents"

    id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    kd_class_code_id = Column(Integer, ForeignKey("class_codes_kd.id"), nullable=False)
    prni = Column(Integer, nullable=False) # 001..9999
    designation = Column(String, unique=True, nullable=False) # КО.ККХ.ПРНИ
    base_doc = relationship("BaseDocument", back_populates="design_document")
    org_code_str = Column(String(8), index=True)
    class_code_str = Column(String(6), index=True)
    organization = relationship("Organization")
    kd_class_code = relationship("ClassCodeKD")

class TechDocument(Base):
    __tablename__ = "tech_documents"
    id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    td_class_code_id = Column(Integer, ForeignKey("class_codes_td.id"), nullable=False)
    prn = Column(Integer, nullable=False)  # 00001..99999
    designation = Column(String, unique=True, nullable=False)  # КО.КХД.ПРН
    organization = relationship("Organization")
    td_class_code = relationship("ClassCodeTD")
    base_doc = relationship("BaseDocument", back_populates="tech_document")