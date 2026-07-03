# app/schemas.py

from pydantic import BaseModel, Field, ConfigDict
from typing import Optional
import enum

from app.models import DocumentStatus


class UserRole(str, enum.Enum):
    master_admin = "master_admin"
    admin = "admin"
    user = "user"
    reviewer = "reviewer"


class UserBase(BaseModel):
    login: str
    full_name: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    role: UserRole = UserRole.user


class UserCreate(BaseModel):
    login: str
    password: str
    full_name: str | None = None
    position: str | None = None
    department: str | None = None
    email: str | None = None


class UserAdminUpdate(BaseModel):
    login: str
    full_name: str | None = None
    position: str | None = None
    department: str | None = None
    role: UserRole = UserRole.user


class User(UserBase):
    id: int
    email: Optional[str] = None
    email_verified: bool = False
    is_active: bool = False
    preferred_org_code: Optional[str] = None
    preferred_org_okpo: bool = False
    visible_columns: Optional[list[str]] = None
    model_config = ConfigDict(from_attributes=True)


class UserProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    position: Optional[str] = None
    department: Optional[str] = None
    email: Optional[str] = None
    preferred_org_code: Optional[str] = None
    preferred_org_okpo: bool = False
    visible_columns: Optional[list[str]] = None


class ProjectBase(BaseModel):
    name: str = Field(..., max_length=255)


class ProjectCreate(ProjectBase):
    pass


class Project(ProjectBase):
    id: int
    slug: str
    model_config = ConfigDict(from_attributes=True)


class OrganizationBase(BaseModel):
    code: Optional[str] = Field(None, max_length=4)
    name: str
    code_okpo: bool = Field(False, description="Флаг использования ОКПО")
    num_code: Optional[int] = Field(None, ge=0, le=99999999)
    num_code_okpo: Optional[int] = Field(None, ge=0, le=99999999)


class OrganizationCreate(OrganizationBase):
    pass


class Organization(OrganizationBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClassCodeKDBase(BaseModel):
    code: str = Field(..., max_length=6)
    description: Optional[str] = None


class ClassCodeKDCreate(ClassCodeKDBase):
    pass


class ClassCodeKD(ClassCodeKDBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class ClassCodeTDBase(BaseModel):
    code: str = Field(..., max_length=7)
    description: Optional[str] = None


class ClassCodeTDCreate(ClassCodeTDBase):
    pass


class ClassCodeTD(ClassCodeTDBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class BaseDocumentBase(BaseModel):
    file_name: Optional[str] = None
    file_path: Optional[str] = None
    created_by: Optional[str] = None
    uploaded_by: int
    position: Optional[str] = None
    department: Optional[str] = None
    type: str
    doc_name: Optional[str] = None
    developed_by: Optional[str] = None
    project_id: int
    status: DocumentStatus = DocumentStatus.pending_review


class BaseDocumentCreate(BaseDocumentBase):
    pass


class BaseDocument(BaseDocumentBase):
    id: int
    created_at: Optional[str] = None
    last_update: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


class DesignDocumentBase(BaseModel):
    org_id: int
    kd_class_code_id: int
    prni: int
    designation: str


class DesignDocumentCreate(DesignDocumentBase):
    base_document_id: int


class DesignDocument(DesignDocumentBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class TechDocumentBase(BaseModel):
    org_id: int
    td_class_code_id: int
    prn: int
    designation: str


class TechDocumentCreate(TechDocumentBase):
    base_document_id: int


class TechDocument(TechDocumentBase):
    id: int
    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str


class DocumentStatusUpdate(BaseModel):
    status: DocumentStatus
    comment: Optional[str] = None
