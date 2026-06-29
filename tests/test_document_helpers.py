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
