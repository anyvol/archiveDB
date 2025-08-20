from pydantic import BaseModel, Field
from typing import Optional, List
import enum

class UserRole(str, enum.Enum):
    admin = "admin"
    user = "user"

class UserBase(BaseModel):
    login: str
    full_name: Optional[str]
    position: Optional[str]
    department: Optional[str]
    role: UserRole = UserRole.user

class UserCreate(BaseModel):
    login: str
    password: str
    full_name: str | None = None
    position: str | None = None
    department: str | None = None
    role: str = "user"

class User(UserBase):
    id: int
    class Config:
        orm_mode = True

class OrganizationBase(BaseModel):
    code: str = Field(..., max_length=8)
    name: str
    department: Optional[str]

class OrganizationCreate(OrganizationBase):
    pass

class Organization(OrganizationBase):
    id: int
    class Config:
        orm_mode = True

class ClassCodeKDBase(BaseModel):
    code: str = Field(..., max_length=6)
    description: Optional[str]

class ClassCodeKDCreate(ClassCodeKDBase):
    pass

class ClassCodeKD(ClassCodeKDBase):
    id: int
    class Config:
        orm_mode = True

class ClassCodeTDBase(BaseModel):
    code: str = Field(..., max_length=7)
    description: Optional[str]

class ClassCodeTDCreate(ClassCodeTDBase):
    pass

class ClassCodeTD(ClassCodeTDBase):
    id: int
    class Config:
        orm_mode = True

class BaseDocumentBase(BaseModel):
    file_name: str
    file_path: str
    created_by: Optional[str]
    uploaded_by: int
    position: Optional[str]
    department: Optional[str]
    type: str  # 'DD' or 'TD'

class BaseDocumentCreate(BaseDocumentBase):
    pass

class BaseDocument(BaseDocumentBase):
    id: int
    created_at: Optional[str]
    class Config:
        orm_mode = True

class DesignDocumentBase(BaseModel):
    org_id: int
    kd_class_code_id: int
    prni: int
    designation: str

class DesignDocumentCreate(DesignDocumentBase):
    base_document_id: int

class DesignDocument(DesignDocumentBase):
    id: int
    class Config:
        orm_mode = True

class TechDocumentBase(BaseModel):
    org_id: int
    td_class_code_id: int
    prn: int
    designation: str

class TechDocumentCreate(TechDocumentBase):
    base_document_id: int

class TechDocument(TechDocumentBase):
    id: int
    class Config:
        orm_mode = True

class Token(BaseModel):
    access_token: str
    token_type: str