# app/models.py

from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum, Boolean
import enum
from datetime import datetime

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
    role = Column(SAEnum(UserRole), default=UserRole.user, nullable=False)

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    code = Column(String(8), nullable=True)
    name = Column(String(255))
    code_okpo = Column(Boolean, default=False)
    num_code = Column(Integer, nullable=True)
    num_code_okpo = Column(Integer, nullable=True)
    design_documents = relationship("DesignDocument", back_populates="org")
    tech_documents = relationship("TechDocument", back_populates="org")

class ClassCodeKD(Base):
    __tablename__ = "class_codes_kd"
    id = Column(Integer, primary_key=True)
    code = Column(String(6), unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

class ClassCodeTD(Base):
    __tablename__ = "class_codes_td"
    id = Column(Integer, primary_key=True)
    code = Column(String(7), unique=True, index=True, nullable=False)
    description = Column(String, nullable=True)

class BaseDocument(Base):
    __tablename__ = "documents"
    
    id = Column(Integer, primary_key=True, index=True)
    file_name = Column(String, unique=True, nullable=True)
    file_path = Column(String, nullable=True)
    type = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_update = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = Column(String, nullable=False)
    developed_by = Column(String, nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    position = Column(String, nullable=True)
    department = Column(String, nullable=True)
    doc_name = Column(String, nullable=True)
    checked = Column(Boolean, default=False, nullable=False)
    
    design_document = relationship(
        "DesignDocument", 
        back_populates="base_document", 
        uselist=False,
        cascade="all, delete-orphan"
    )
    tech_document = relationship(
        "TechDocument", 
        back_populates="base_document", 
        uselist=False,
        cascade="all, delete-orphan"
    )

class DesignDocument(Base):
    __tablename__ = "design_documents"

    id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    kd_class_code_id = Column(Integer, ForeignKey("class_codes_kd.id"), nullable=False)
    prni = Column(Integer, nullable=False)
    designation = Column(String, unique=True, nullable=False)
    
    org_code_str = Column(String(8), index=True)
    class_code_str = Column(String(6), index=True)
    doc_kind_code = Column(String(3), nullable=True)  # Код вида по ГОСТ Р 2.102-2023 (e.g., "СБ")
    
    base_document = relationship("BaseDocument", back_populates="design_document")
    kd_class_code = relationship("ClassCodeKD")
    org = relationship("Organization", back_populates="design_documents", foreign_keys=[org_id])

class TechDocument(Base):
    __tablename__ = "tech_documents"

    id = Column(Integer, ForeignKey("documents.id"), primary_key=True)
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=False)
    td_class_code_id = Column(Integer, ForeignKey("class_codes_td.id"), nullable=False)
    prn = Column(Integer, nullable=False)
    designation = Column(String, unique=True, nullable=False)
    
    org_code_str = Column(String(8), index=True)
    class_code_str = Column(String(7), index=True)
    
    base_document = relationship("BaseDocument", back_populates="tech_document")
    td_class_code = relationship("ClassCodeTD")
    org = relationship("Organization", back_populates="tech_documents", foreign_keys=[org_id])
