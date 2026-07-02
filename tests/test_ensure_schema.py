"""Tests for schema repair helper."""

from scripts.ensure_schema import _sync_database_url


def test_sync_database_url_from_asyncpg():
    url = "postgresql+asyncpg://user:pass@db:5432/archivedb"
    assert _sync_database_url(url) == "postgresql+psycopg2://user:pass@db:5432/archivedb"
