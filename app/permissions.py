"""Centralized role and document permission checks."""

from fastapi import HTTPException, status

from app.models import BaseDocument, DocumentStatus, User, UserRole
from app.change_log import is_governed_document


def is_admin(user: User) -> bool:
    return user.role == UserRole.admin


def is_reviewer(user: User) -> bool:
    return user.role == UserRole.reviewer


def is_reviewer_or_admin(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.reviewer)


def is_owner(user: User, doc: BaseDocument) -> bool:
    return doc.uploaded_by == user.id


def can_create_document(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.user)


def can_set_document_status(user: User) -> bool:
    return is_reviewer_or_admin(user)


def can_delete_document(user: User) -> bool:
    return is_admin(user)


def can_edit_document_metadata(user: User, doc: BaseDocument) -> bool:
    if doc.status == DocumentStatus.pending_review:
        return False
    if is_admin(user):
        return True
    if is_owner(user, doc):
        return doc.status in (DocumentStatus.approved, DocumentStatus.requires_correction)
    return False


def can_upload_file(user: User, doc: BaseDocument) -> bool:
    """Replace or first upload. For КД/ТД governed docs, replace only when requires_correction."""
    if not doc.file_name:
        return True

    if is_governed_document(doc):
        return doc.status == DocumentStatus.requires_correction

    if is_admin(user):
        return True
    if not is_owner(user, doc):
        return False
    return doc.status == DocumentStatus.requires_correction


def can_request_minor_correction(user: User, doc: BaseDocument) -> bool:
    """Any user may request minor correction while document is on review (КД/ТД only)."""
    if not is_governed_document(doc):
        return False
    if not doc.file_name:
        return False
    return doc.status == DocumentStatus.pending_review


def can_respond_correction_request(user: User, doc: BaseDocument) -> bool:
    return is_reviewer_or_admin(user) and doc.status == DocumentStatus.correction_requested


def can_apply_formal_change(user: User, doc: BaseDocument) -> bool:
    """Formal change with ИИ for approved КД/ТД documents."""
    if not is_governed_document(doc):
        return False
    if not doc.file_name:
        return False
    return doc.status == DocumentStatus.approved


def can_open_document_card(user: User) -> bool:
    return user.role in (UserRole.admin, UserRole.user, UserRole.reviewer)


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
