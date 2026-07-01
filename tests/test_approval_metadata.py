"""Tests for approval metadata validation."""

import pytest
from fastapi import HTTPException

from app.document_helpers import validate_approval_metadata


class _Doc:
    def __init__(self, reviewed_by=None, approved_by=None):
        self.reviewed_by = reviewed_by
        self.approved_by = approved_by


def test_validate_approval_metadata_ok():
    validate_approval_metadata(_Doc(reviewed_by="Иванов", approved_by="Петров"))


def test_validate_approval_metadata_missing_fields():
    with pytest.raises(HTTPException) as exc:
        validate_approval_metadata(_Doc())
    assert "ФИО проверяющего" in exc.value.detail
    assert "ФИО утверждающего" in exc.value.detail
