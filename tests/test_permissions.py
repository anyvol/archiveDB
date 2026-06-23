import pytest

from app.models import BaseDocument, DocumentStatus, User, UserRole
from app.permissions import (
    can_create_document,
    can_delete_document,
    can_edit_document_metadata,
    can_set_document_status,
    can_upload_file,
)


def _user(role: UserRole, user_id: int = 1) -> User:
    u = User(id=user_id, login="test", password_hash="x", role=role)
    return u


def _doc(uploaded_by: int = 1, file_name: str | None = None, status=DocumentStatus.pending_review) -> BaseDocument:
    return BaseDocument(
        id=1,
        type="DD",
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


def test_user_cannot_replace_while_pending():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.pending_review)
    assert not can_upload_file(_user(UserRole.user, 1), doc)


def test_user_can_replace_when_requires_correction():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.requires_correction)
    assert can_upload_file(_user(UserRole.user, 1), doc)


def test_user_cannot_replace_when_verified():
    doc = _doc(uploaded_by=1, file_name="file.pdf", status=DocumentStatus.verified)
    assert not can_upload_file(_user(UserRole.user, 1), doc)


def test_admin_can_always_upload():
    doc = _doc(uploaded_by=99, file_name="file.pdf", status=DocumentStatus.verified)
    assert can_upload_file(_user(UserRole.admin), doc)


def test_only_admin_edits_metadata():
    doc = _doc()
    assert can_edit_document_metadata(_user(UserRole.admin), doc)
    assert not can_edit_document_metadata(_user(UserRole.user), doc)
