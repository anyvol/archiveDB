# app/models.py

from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum, Boolean, Text, JSON
import enum
from datetime import datetime

Base = declarative_base()


class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"
    reviewer = "reviewer"


class DocumentStatus(str, enum.Enum):
    pending_review = "pending_review"
    verified = "verified"
    requires_correction = "requires_correction"


class NotificationEventType(str, enum.Enum):
    upload = "upload"
    status_change = "status_change"
    document_edit = "document_edit"
    document_register = "document_register"
    document_delete = "document_delete"


DOCUMENT_STATUS_LABELS = {
    DocumentStatus.pending_review: "На проверке",
    DocumentStatus.verified: "Проверено",
    DocumentStatus.requires_correction: "Требуется исправление",
}

DISPLAY_STATUS_NO_FILE = "Файл не загружен"

DOCUMENT_TYPE_LABELS = {
    "DD": "КД",
    "TD": "ТД",
}

DOC_KIND_CODES = ("СБ", "СП", "ГЧ", "ТУ", "Э2", "Е1", "РЭ", "ВП", "ПС")

MISC_DOCS_FOLDER = "Прочие документы"

DEPARTMENTS = [
    "Конструкторский отдел",
    "Технологический отдел",
    "Отдел НИОКР",
]


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    login = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    full_name = Column(String, nullable=True)
    position = Column(String, nullable=True)
    department = Column(String, nullable=True)
    role = Column(SAEnum(UserRole), default=UserRole.user, nullable=False)
    email = Column(String(100), nullable=True)
    preferred_org_code = Column(String(8), nullable=True)
    preferred_org_okpo = Column(Boolean, default=False, nullable=False)
    visible_columns = Column(JSON, nullable=True)
    notifications = relationship("Notification", back_populates="user")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=True)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    event_type = Column(SAEnum(NotificationEventType), nullable=False)

    user = relationship("User", back_populates="notifications")
    document = relationship("BaseDocument")


class Project(Base):
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True)
    name = Column(String(255), unique=True, nullable=False)
    slug = Column(String(255), unique=True, nullable=False)
    documents = relationship("BaseDocument", back_populates="project")


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
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    status = Column(
        SAEnum(DocumentStatus),
        default=DocumentStatus.pending_review,
        nullable=False,
    )
    review_comment = Column(Text, nullable=True)
    registration_notified_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="documents")
    design_document = relationship(
        "DesignDocument",
        back_populates="base_document",
        uselist=False,
        cascade="all, delete-orphan",
    )
    tech_document = relationship(
        "TechDocument",
        back_populates="base_document",
        uselist=False,
        cascade="all, delete-orphan",
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
    doc_kind_code = Column(String(3), nullable=True)

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
