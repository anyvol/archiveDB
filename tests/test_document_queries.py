"""Tests for document query filter params."""

from datetime import datetime

from app.document_queries import build_documents_query, SORTABLE_COLUMNS


def test_sortable_columns_include_org_and_project():
    assert "org_name" in SORTABLE_COLUMNS
    assert "project" in SORTABLE_COLUMNS


def test_build_query_accepts_org_name_and_project_id():
    query = build_documents_query(org_name="Организация", project_id=1)
    assert query is not None


def test_build_query_accepts_timezone_name():
    query = build_documents_query(
        created_from="2026-07-03",
        created_to="2026-07-03",
        timezone_name="Europe/Moscow",
    )
    assert query is not None
