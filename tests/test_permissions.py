import pytest

from app.models import BaseDocument, DocumentStatus, User, UserRole
from app.permissions import (
    can_apply_formal_change,
    can_create_document,
    can_delete_document,
    can_edit_document_metadata,
    can_request_minor_correction,
    can_set_document_status,
    can_upload_file,
)


def _user(role: UserRole, user_id: int = 1) -> User:
    u = User(id=user_id, login="test", password_hash="x", role=role)
    return u


def _doc(uploaded_by: int = 1, file_name: str | None = None, status=DocumentStatus.pending_review, doc_type="DD") -> BaseDocument:
    return BaseDocument(
        id=1,
        type=doc_type,
        created_by="Author",
        uploaded_by=uploaded_by,
        status=status,
        file_name=file_name,
    )


def test_user_can_create_document():
    assert can_create_document(_user(UserRole.user))
    assert can_create_document(_user(UserRole.admin))
    assert not can_create_document(_user(UserRole.reviewer))


def test_reviewer_can_set_status():
    assert can_set_document_status(_user(UserRole.reviewer))
    assert can_set_document_status(_user(UserRole.admin))
    assert not can_set_document_status(_user(UserRole.user))


def test_only_admin_can_delete():
    assert can_delete_document(_user(UserRole.admin))
    assert not can_delete_document(_user(UserRole.user))
    assert not can_delete_document(_user(UserRole.reviewer))


def test_user_first_upload_allowed():
    doc = _doc(uploaded_by=1, file_name=None)
    assert can_upload_file(_user(UserRole.user, 1), doc)


def test_any_user_can_first_upload_without_file():
    doc = _doc(uploaded_by=99, file_name=None)
    assert can_upload_file(_user(UserRole.user, 1), doc)


def test_user_cannot_replace_while_pending():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.pending_review)
    assert not can_upload_file(_user(UserRole.user, 1), doc)


def test_user_can_replace_when_requires_correction():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.requires_correction)
    assert can_upload_file(_user(UserRole.user, 1), doc)


def test_any_user_can_replace_when_requires_correction():
    doc = _doc(uploaded_by=99, file_name="file.pdf", status=DocumentStatus.requires_correction)
    assert can_upload_file(_user(UserRole.user, 1), doc)


def test_user_cannot_replace_when_approved():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.approved)
    assert not can_upload_file(_user(UserRole.user, 1), doc)


def test_admin_cannot_replace_approved_kd():
    doc = _doc(uploaded_by=99, file_name="file.pdf", status=DocumentStatus.approved)
    assert not can_upload_file(_user(UserRole.admin), doc)


def test_edit_metadata_rules():
    pending = _doc(status=DocumentStatus.pending_review)
    approved = _doc(uploaded_by=1, status=DocumentStatus.approved)
    correction = _doc(uploaded_by=1, status=DocumentStatus.requires_correction)

    assert not can_edit_document_metadata(_user(UserRole.admin), pending)
    assert can_edit_document_metadata(_user(UserRole.admin), approved)

    assert not can_edit_document_metadata(_user(UserRole.user, 1), pending)
    assert can_edit_document_metadata(_user(UserRole.user, 1), approved)
    assert can_edit_document_metadata(_user(UserRole.user, 1), correction)
    assert not can_edit_document_metadata(_user(UserRole.user, 2), approved)


def test_request_minor_correction():
    doc = _doc(file_name="a.pdf", status=DocumentStatus.pending_review)
    assert can_request_minor_correction(_user(UserRole.user), doc)
    assert not can_request_minor_correction(_user(UserRole.user), _doc(file_name="a.pdf", status=DocumentStatus.approved))


def test_apply_formal_change():
    doc = _doc(file_name="a.pdf", status=DocumentStatus.approved)
    assert can_apply_formal_change(_user(UserRole.user), doc)
    assert not can_apply_formal_change(_user(UserRole.user), _doc(file_name="a.pdf", status=DocumentStatus.pending_review))
