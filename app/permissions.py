"""Centralized role and document permission checks."""

from fastapi import HTTPException, status

from app.models import BaseDocument, DocumentStatus, User, UserRole
from app.change_log import is_governed_document
from app.role_permissions import role_has_permission


def is_master_admin(user: User) -> bool:
    return user.role == UserRole.master_admin


def is_admin(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.master_admin)


def is_reviewer(user: User) -> bool:
    return user.role == UserRole.reviewer


def is_reviewer_or_admin(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.master_admin, UserRole.reviewer)


def is_owner(user: User, doc: BaseDocument) -> bool:
    return doc.uploaded_by == user.id


def _has(user: User, permission_key: str) -> bool:
    return role_has_permission(user.role, permission_key)


def can_manage_project(user: User) -> bool:
    return _has(user, "manage_projects")


def user_has_full_access(user: User) -> bool:
    if user.role != UserRole.user:
        return True
    return bool(user.access_granted)


def require_full_access(user: User) -> None:
    if not user_has_full_access(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="access_code_required",
        )


def can_create_document(user: User) -> bool:
    return _has(user, "create_document")


def can_set_document_status(user: User) -> bool:
    return _has(user, "set_document_status")


def can_delete_document(user: User) -> bool:
    return _has(user, "delete_document")


def can_add_document_links(user: User) -> bool:
    return _has(user, "add_document_links")


def can_remove_document_links(user: User) -> bool:
    return _has(user, "remove_document_links")


def can_add_applicability(user: User) -> bool:
    return _has(user, "add_applicability")


def can_remove_applicability(user: User) -> bool:
    return _has(user, "remove_applicability")


def can_edit_document_metadata(user: User, doc: BaseDocument) -> bool:
    if doc.status == DocumentStatus.pending_review:
        return False
    if _has(user, "edit_document_metadata"):
        return True
    if is_owner(user, doc) and _has(user, "edit_own_document_metadata"):
        return doc.status in (DocumentStatus.approved, DocumentStatus.requires_correction)
    return False


def can_upload_file(user: User, doc: BaseDocument) -> bool:
    """Replace or first upload. For КД/ТД governed docs, replace only when requires_correction."""
    if not doc.file_name:
        return True

    if is_governed_document(doc):
        return doc.status == DocumentStatus.requires_correction

    if _has(user, "upload_file") and is_admin(user):
        return True
    if not _has(user, "upload_file"):
        return False
    if not is_owner(user, doc):
        return False
    return doc.status == DocumentStatus.requires_correction


def can_request_minor_correction(user: User, doc: BaseDocument) -> bool:
    """Any user may request minor correction while document is on review (КД/ТД only)."""
    if not _has(user, "request_minor_correction"):
        return False
    if not is_governed_document(doc):
        return False
    if not doc.file_name:
        return False
    return doc.status == DocumentStatus.pending_review


def can_respond_correction_request(user: User, doc: BaseDocument) -> bool:
    return _has(user, "respond_correction_request") and doc.status == DocumentStatus.correction_requested


def can_apply_formal_change(user: User, doc: BaseDocument) -> bool:
    """Formal change with ИИ for approved КД/ТД documents."""
    if not _has(user, "apply_formal_change"):
        return False
    if not is_governed_document(doc):
        return False
    if not doc.file_name:
        return False
    return doc.status == DocumentStatus.approved


def can_open_document_card(user: User) -> bool:
    return _has(user, "view_documents")


def require_upload_permission(user: User, doc: BaseDocument) -> None:
    if not can_upload_file(user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Замена файла доступна только при статусе «Требуется исправление».",
        )


def require_status_change_permission(user: User) -> None:
    if not can_set_document_status(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Недостаточно прав для изменения статуса.",
        )


def require_delete_permission(user: User) -> None:
    if not can_delete_document(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Удаление доступно только администратору.",
        )


def require_edit_metadata_permission(user: User, doc: BaseDocument) -> None:
    if not can_edit_document_metadata(user, doc):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Редактирование метаданных доступно только администратору.",
        )
