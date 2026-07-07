"""Tests for document file path helpers."""

import os

from app.document_helpers import (
    _resolve_upload_subdirectory,
    build_upload_rename_message,
    compute_stored_file_name,
    _sanitize_storage_name,
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


def test_sanitize_storage_name():
    assert _sanitize_storage_name('bad<>name.pdf') == "bad__name.pdf"
