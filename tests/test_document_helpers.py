"""Tests for document file path helpers."""

import os

from app.document_helpers import (
    _resolve_upload_subdirectory,
    build_upload_rename_message,
    compute_stored_file_name,
    compose_display_file_name,
    extract_stored_file_name,
    file_name_matches_designation,
    resolve_record_display_name,
    _sanitize_storage_name,
    validate_approval_metadata,
)
from app.models import DOC_KIND_CODES, MISC_DOCS_FOLDER


def test_resolve_upload_subdirectory_project_root():
    path = _resolve_upload_subdirectory("my-project")
    assert path.endswith(os.path.join("uploaded_files", "my-project"))


def test_resolve_upload_subdirectory_doc_kind():
    for code in DOC_KIND_CODES:
        path = _resolve_upload_subdirectory("my-project", doc_kind_code=code)
        assert path.endswith(os.path.join("my-project", code))


def test_resolve_upload_subdirectory_misc_documents():
    path = _resolve_upload_subdirectory("my-project", misc_document=True)
    assert path.endswith(os.path.join("my-project", MISC_DOCS_FOLDER))


def test_compute_stored_file_name_renames_when_designation_differs():
    assert compute_stored_file_name("ORG.123456.001", "other.pdf") == "ORG.123456.001(other).pdf"
    assert compute_stored_file_name("ORG.123456.001", "ORG.123456.001.pdf") == "ORG.123456.001.pdf"
    assert compute_stored_file_name(None, "report.pdf") == "report.pdf"


def test_file_name_matches_designation():
    assert file_name_matches_designation("ORG.123456.001.pdf", "ORG.123456.001")
    assert not file_name_matches_designation("other.pdf", "ORG.123456.001")


def test_build_upload_rename_message():
    assert build_upload_rename_message("ORG.123456.001", "other.pdf") == (
        "Файл будет переименован в ORG.123456.001(other).pdf"
    )


def test_sanitize_storage_name():
    assert _sanitize_storage_name('bad<>name.pdf') == "bad__name.pdf"


def test_compose_display_file_name():
    assert compose_display_file_name("doc.pdf", "Наименование") == "doc.pdf Наименование"
    assert compose_display_file_name("doc.pdf", None) == "doc.pdf"
    assert compose_display_file_name("doc.pdf", "  ") == "doc.pdf"


def test_extract_stored_file_name():
    assert extract_stored_file_name("doc.pdf Наименование", "Наименование") == "doc.pdf"
    assert extract_stored_file_name("doc.pdf", "Наименование") == "doc.pdf"


def test_resolve_record_display_name():
    assert resolve_record_display_name("Title", "ORG.001") == "Title"
    assert resolve_record_display_name(None, "ORG.001") == "ORG.001"
    assert resolve_record_display_name("", None) is None
