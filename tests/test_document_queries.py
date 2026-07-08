"""Tests for document query filter params."""

from datetime import datetime

from app.document_queries import _local_date_boundary, build_documents_query, SORTABLE_COLUMNS


def test_sortable_columns_include_org_and_project():
    assert "org_name" in SORTABLE_COLUMNS
    assert "project" in SORTABLE_COLUMNS
    assert "product" in SORTABLE_COLUMNS


def test_build_query_accepts_org_name_project_id_and_product_id():
    query = build_documents_query(org_name="Организация", project_id=1, product_id=5)
    assert query is not None


def test_local_date_boundary_converts_admin_timezone_to_utc_day_range():
    start = _local_date_boundary("2026-01-02", "Europe/Moscow")
    end = _local_date_boundary("2026-01-02", "Europe/Moscow", end_of_day=True)

    assert start == datetime(2026, 1, 1, 21, 0, 0)
    assert end.date().isoformat() == "2026-01-02"
    assert end.hour == 20
    assert end.minute == 59
    assert end.second == 59
