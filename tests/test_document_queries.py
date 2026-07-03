"""Tests for document query filter params."""

from app.document_queries import DOCUMENTS_PAGE_SIZE, SORTABLE_COLUMNS, build_documents_query


def test_documents_page_size_is_twenty():
    assert DOCUMENTS_PAGE_SIZE == 20


def test_sortable_columns_include_org_and_project():
    assert "org_name" in SORTABLE_COLUMNS
    assert "project" in SORTABLE_COLUMNS


def test_build_query_accepts_org_name_and_project_id():
    query = build_documents_query(org_name="Организация", project_id=1)
    assert query is not None
