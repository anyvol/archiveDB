"""Tests for document file path helpers."""

import os

from app.document_helpers import _resolve_upload_subdirectory
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


def test_compute_stored_file_name():
    from app.document_helpers import (
        build_upload_rename_message,
        compute_stored_file_name,
        file_name_matches_designation,
    )

    assert compute_stored_file_name("report.pdf", 42) == "report_42.pdf"
    assert file_name_matches_designation("ORG.123456.001.pdf", "ORG.123456.001")
    assert not file_name_matches_designation("other.pdf", "ORG.123456.001")
    assert build_upload_rename_message("ORG.123456.001", "other.pdf") == (
        "Файл будет переименован в ORG.123456.001(other.pdf)"
    )
