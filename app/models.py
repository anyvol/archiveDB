# app/models.py

from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy import Column, Integer, String, ForeignKey, DateTime, Enum as SAEnum, Boolean, Text, JSON, UniqueConstraint
import enum
from datetime import datetime

Base = declarative_base()


class UserRole(str, enum.Enum):
    master_admin = "master_admin"
    admin = "admin"
    user = "user"
    reviewer = "reviewer"


USER_ROLE_LABELS = {
    UserRole.master_admin: "Главный администратор",
    UserRole.admin: "Администратор",
    UserRole.user: "Обычный пользователь",
    UserRole.reviewer: "Ревьюер",
}


class DocumentStatus(str, enum.Enum):
    pending_review = "pending_review"
    approved = "approved"
    requires_correction = "requires_correction"
    correction_requested = "correction_requested"


class NotificationEventType(str, enum.Enum):
    upload = "upload"
    status_change = "status_change"
    document_edit = "document_edit"
    document_register = "document_register"
    document_delete = "document_delete"
    correction_request = "correction_request"
    correction_request_response = "correction_request_response"
    formal_change = "formal_change"


class DocumentChangeEventType(str, enum.Enum):
    register = "register"
    file_upload = "file_upload"
    file_replace_cosmetic = "file_replace_cosmetic"
    file_replace_formal = "file_replace_formal"
    metadata_edit = "metadata_edit"
    status_change = "status_change"
    correction_request = "correction_request"
    correction_request_approved = "correction_request_approved"
    correction_request_rejected = "correction_request_rejected"


DOCUMENT_CHANGE_EVENT_LABELS = {
    DocumentChangeEventType.register: "Регистрация записи",
    DocumentChangeEventType.file_upload: "Загрузка файла",
    DocumentChangeEventType.file_replace_cosmetic: "Косметическое исправление файла",
    DocumentChangeEventType.file_replace_formal: "Изменение по извещению",
    DocumentChangeEventType.metadata_edit: "Изменение метаданных",
    DocumentChangeEventType.status_change: "Изменение статуса",
    DocumentChangeEventType.correction_request: "Запрос на исправление",
    DocumentChangeEventType.correction_request_approved: "Запрос на исправление одобрен",
    DocumentChangeEventType.correction_request_rejected: "Запрос на исправление отклонён",
}


DOCUMENT_STATUS_LABELS = {
    DocumentStatus.pending_review: "На проверке",
    DocumentStatus.approved: "Утверждено",
    DocumentStatus.requires_correction: "Требуется исправление",
    DocumentStatus.correction_requested: "Запрошено исправление",
}

DISPLAY_STATUS_NO_FILE = "Файл не загружен"

DOCUMENT_TYPE_LABELS = {
    "DD": "КД",
    "TD": "ТД",
}

DOC_KIND_CODES = ("СБ", "СП", "ГЧ", "ТУ", "Э2", "Е1", "РЭ", "ВП", "ПС")

GOVERNED_DOCUMENT_TYPES = ("DD", "TD")

MISC_DOCS_FOLDER = "Прочие документы"
II_FOLDER = "Извещения об изменении"
VERSIONS_FOLDER = "versions"
IMAGES_FOLDER = "изображения"

DEPARTMENTS = [
    "Конструкторский отдел",
    "Технологический отдел",
    "Отдел НИОКР",
    "Отдел интеграции и сопровождения",
    "Сервисный отдел",
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
    email = Column(String(100), nullable=True, unique=True, index=True)
    email_verified = Column(Boolean, default=False, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    access_granted = Column(Boolean, default=False, nullable=False)
    preferred_org_code = Column(String(8), nullable=True)
    preferred_org_okpo = Column(Boolean, default=False, nullable=False)
    visible_columns = Column(JSON, nullable=True)
    push_subscription = Column(JSON, nullable=True)
    push_preferences = Column(JSON, nullable=True)
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
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)
    documents = relationship("BaseDocument", back_populates="project")
    products = relationship(
        "Product",
        back_populates="project",
        order_by="Product.name",
        cascade="all, delete-orphan",
    )
    project_files = relationship(
        "ProjectFile",
        back_populates="project",
        order_by="ProjectFile.created_at.desc()",
    )
    project_images = relationship(
        "ProjectImage",
        back_populates="project",
        order_by="ProjectImage.created_at.desc()",
    )


class Product(Base):
    """Изделие внутри проекта."""

    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_products_project_name"),
        UniqueConstraint("project_id", "slug", name="uq_products_project_slug"),
    )

    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    slug = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="products")
    documents = relationship("BaseDocument", back_populates="product")
    applicability_entries = relationship(
        "DocumentApplicability",
        back_populates="product",
        cascade="all, delete-orphan",
    )


class ProjectFile(Base):
    __tablename__ = "project_files"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="project_files")
    uploader = relationship("User")


class ProjectImage(Base):
    __tablename__ = "project_images"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False, index=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    project = relationship("Project", back_populates="project_images")


class DocumentApplicability(Base):
    """Учёт применяемости документа в других изделиях (ГОСТ 2.501-2013)."""

    __tablename__ = "document_applicability"
    __table_args__ = (
        UniqueConstraint("document_id", "product_id", name="uq_document_applicability_doc_product"),
    )

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id = Column(Integer, ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    file_path = Column(String, nullable=False)
    file_name = Column(String, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    document = relationship("BaseDocument", back_populates="applicability_entries", foreign_keys=[document_id])
    product = relationship("Product", back_populates="applicability_entries")
    creator = relationship("User")


class DocumentLink(Base):
    """Ссылки между записями архива."""

    __tablename__ = "document_links"

    id = Column(Integer, primary_key=True, index=True)
    source_document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    target_document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    source_document = relationship("BaseDocument", back_populates="outgoing_links", foreign_keys=[source_document_id])
    target_document = relationship("BaseDocument", back_populates="incoming_links", foreign_keys=[target_document_id])
    creator = relationship("User")


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
    reviewed_by = Column(String, nullable=True)
    approved_by = Column(String, nullable=True)
    developer_signed_date = Column(String(32), nullable=True)
    reviewer_signed_date = Column(String(32), nullable=True)
    approver_signed_date = Column(String(32), nullable=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    position = Column(String, nullable=True)
    department = Column(String, nullable=True)
    doc_name = Column(String, nullable=True)
    document_format = Column(String(32), nullable=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True)
    status = Column(
        SAEnum(DocumentStatus),
        default=DocumentStatus.pending_review,
        nullable=False,
    )
    review_comment = Column(Text, nullable=True)
    correction_request_comment = Column(Text, nullable=True)
    registration_notified_at = Column(DateTime, nullable=True)

    project = relationship("Project", back_populates="documents")
    product = relationship("Product", back_populates="documents")
    change_events = relationship(
        "DocumentChangeEvent",
        back_populates="document",
        order_by="DocumentChangeEvent.created_at.desc()",
        cascade="all, delete-orphan",
    )
    file_revisions = relationship(
        "FileRevision",
        back_populates="document",
        order_by="FileRevision.archived_at.desc()",
        cascade="all, delete-orphan",
    )
    change_notifications = relationship(
        "ChangeNotification",
        back_populates="document",
        order_by="ChangeNotification.created_at.desc()",
        cascade="all, delete-orphan",
    )
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
    applicability_entries = relationship(
        "DocumentApplicability",
        back_populates="document",
        foreign_keys="DocumentApplicability.document_id",
        cascade="all, delete-orphan",
    )
    outgoing_links = relationship(
        "DocumentLink",
        back_populates="source_document",
        foreign_keys="DocumentLink.source_document_id",
        cascade="all, delete-orphan",
    )
    incoming_links = relationship(
        "DocumentLink",
        back_populates="target_document",
        foreign_keys="DocumentLink.target_document_id",
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
    execution = Column(String(4), nullable=True)
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


class FileRevision(Base):
    __tablename__ = "file_revisions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    archived_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    revision_label = Column(String, nullable=True)

    document = relationship("BaseDocument", back_populates="file_revisions")


class ChangeNotification(Base):
    """Извещение об изменении (ИИ) — основание для формального изменения документа."""

    __tablename__ = "change_notifications"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    number = Column(String(64), nullable=False)
    date = Column(DateTime, nullable=False)
    file_name = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    developer_signed = Column(Boolean, default=False, nullable=False)
    reviewer_signed = Column(Boolean, default=False, nullable=False)
    approver_signed = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    document = relationship("BaseDocument", back_populates="change_notifications")
    created_by = relationship("User")
    change_event = relationship("DocumentChangeEvent", back_populates="change_notification", uselist=False)


class DocumentChangeEvent(Base):
    """Электронный журнал изменений документа."""

    __tablename__ = "document_change_events"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id"), nullable=False, index=True)
    actor_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_type = Column(SAEnum(DocumentChangeEventType), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    comment = Column(Text, nullable=True)
    change_number = Column(String(64), nullable=True)
    change_date = Column(DateTime, nullable=True)
    change_notification_id = Column(Integer, ForeignKey("change_notifications.id"), nullable=True)
    file_revision_id = Column(Integer, ForeignKey("file_revisions.id"), nullable=True)
    payload = Column(JSON, nullable=True)

    document = relationship("BaseDocument", back_populates="change_events")
    actor = relationship("User")
    change_notification = relationship("ChangeNotification", back_populates="change_event")
    file_revision = relationship("FileRevision")


class SystemSetting(Base):
    __tablename__ = "system_settings"

    key = Column(String(64), primary_key=True)
    value = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)


class EmailVerificationCode(Base):
    __tablename__ = "email_verification_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")


class AdminAccessCode(Base):
    __tablename__ = "admin_access_codes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime, nullable=False)
    attempts = Column(Integer, default=0, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", foreign_keys=[user_id])
    created_by = relationship("User", foreign_keys=[created_by_id])


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    used_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User")


class BackupRecord(Base):
    __tablename__ = "backup_records"

    id = Column(Integer, primary_key=True, index=True)
    backup_id = Column(String(64), unique=True, nullable=False, index=True)
    backup_type = Column(String(32), nullable=False)
    file_path = Column(String(512), nullable=False)
    size_bytes = Column(Integer, nullable=True)
    status = Column(String(32), nullable=False, default="completed")
    checksum_sha256 = Column(String(64), nullable=True)
    triggered_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
