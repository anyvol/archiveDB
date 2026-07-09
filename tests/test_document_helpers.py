"""Tests for document file path helpers."""

import os
import tempfile
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.document_helpers import (
    _resolve_upload_subdirectory,
    build_upload_rename_message,
    compute_stored_file_name,
    compute_renamed_file_name_for_doc_name_change,
    _sanitize_storage_name,
    rename_document_file_for_doc_name,
)
from app.models import DOC_KIND_CODES, MISC_DOCS_FOLDER


def test_resolve_upload_subdirectory_project_root():
    path = _resolve_upload_subdirectory("my-project")
    assert path.endswith(os.path.join("uploaded_files", "my-project"))


def test_resolve_upload_subdirectory_with_product():
    path = _resolve_upload_subdirectory("my-project", product_slug="product-a")
    assert path.endswith(os.path.join("uploaded_files", "my-project", "product-a"))


def test_resolve_upload_subdirectory_doc_kind():
    for code in DOC_KIND_CODES:
        path = _resolve_upload_subdirectory("my-project", product_slug="product-a", doc_kind_code=code)
        assert path.endswith(os.path.join("my-project", "product-a", code))


def test_resolve_upload_subdirectory_misc_documents():
    path = _resolve_upload_subdirectory("my-project", misc_document=True)
    assert path.endswith(os.path.join("my-project", MISC_DOCS_FOLDER))


def test_compute_stored_file_name_when_upload_name_differs_from_designation():
    assert compute_stored_file_name("ORG.123456.001", "other.pdf", "Report") == (
        "ORG.123456.001 (other) - Report.pdf"
    )


def test_compute_stored_file_name_when_upload_name_matches_designation():
    assert compute_stored_file_name("ORG.123456.001", "ORG.123456.001.pdf", "Report") == (
        "ORG.123456.001 - Report.pdf"
    )


def test_compute_stored_file_name_keeps_existing_stored_name():
    stored = "ORG.123456.001 (other) - Report.pdf"
    assert compute_stored_file_name("ORG.123456.001", stored, "Report") == stored


def test_compute_stored_file_name_without_designation():
    assert compute_stored_file_name(None, "report.pdf", "Report") == "report.pdf"


def test_build_upload_rename_message():
    assert build_upload_rename_message("ORG.123456.001", "other.pdf", "Report") == (
        "Файл будет переименован в ORG.123456.001 (other) - Report.pdf"
    )


def test_compute_renamed_file_name_for_doc_name_change_simple_pattern():
    assert compute_renamed_file_name_for_doc_name_change(
        "ORG.123456.001", "ORG.123456.001 - Old Title.pdf", "New Title"
    ) == "ORG.123456.001 - New Title.pdf"


def test_compute_renamed_file_name_for_doc_name_change_paren_pattern():
    assert compute_renamed_file_name_for_doc_name_change(
        "ORG.123456.001", "ORG.123456.001 (other) - Old Title.pdf", "New Title"
    ) == "ORG.123456.001 (other) - New Title.pdf"


def test_sanitize_storage_name():
    assert _sanitize_storage_name('bad<>name.pdf') == "bad__name.pdf"


def test_rename_document_file_for_doc_name_renames_on_disk():
    with tempfile.TemporaryDirectory() as tmpdir:
        old_name = "ORG.123456.001 - Old Title.pdf"
        old_path = os.path.join(tmpdir, old_name)
        with open(old_path, "wb") as f:
            f.write(b"content")

        doc = SimpleNamespace(
            file_path=old_path,
            file_name=old_name,
        )
        old_file_name, new_file_name = rename_document_file_for_doc_name(
            doc, "New Title", designation="ORG.123456.001"
        )
        assert old_file_name == old_name
        assert new_file_name == "ORG.123456.001 - New Title.pdf"
        assert doc.file_name == new_file_name
        assert os.path.exists(doc.file_path)
        assert not os.path.exists(old_path)


def test_rename_document_file_for_doc_name_skips_when_unchanged():
    with tempfile.TemporaryDirectory() as tmpdir:
        name = "ORG.123456.001 - Report.pdf"
        path = os.path.join(tmpdir, name)
        with open(path, "wb") as f:
            f.write(b"content")

        doc = SimpleNamespace(file_path=path, file_name=name)
        result = rename_document_file_for_doc_name(doc, "Report", designation="ORG.123456.001")
        assert result == (None, None)
        assert doc.file_name == name
        assert doc.file_path == path


def test_rename_document_file_for_doc_name_no_file():
    doc = SimpleNamespace(file_path=None, file_name=None)
    assert rename_document_file_for_doc_name(doc, "Title", designation="ORG.123456.001") == (None, None)


def test_rename_document_file_for_doc_name_conflict():
    with tempfile.TemporaryDirectory() as tmpdir:
        existing = os.path.join(tmpdir, "ORG.123456.001 - New Title.pdf")
        with open(existing, "wb") as f:
            f.write(b"existing")

        old_name = "ORG.123456.001 - Old Title.pdf"
        old_path = os.path.join(tmpdir, old_name)
        with open(old_path, "wb") as f:
            f.write(b"content")

        doc = SimpleNamespace(file_path=old_path, file_name=old_name)
        with pytest.raises(HTTPException) as exc:
            rename_document_file_for_doc_name(doc, "New Title", designation="ORG.123456.001")
        assert exc.value.status_code == 409
