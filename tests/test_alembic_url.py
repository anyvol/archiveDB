import pytest

from app.migration_config import resolve_alembic_url, verify_schema


def test_resolve_alembic_url_prefers_docker_db_over_localhost():
    url = resolve_alembic_url(
        database_url="postgresql+asyncpg://archiveuser:secret@db:5432/archivedb",
        alembic_database_url="postgresql+psycopg2://archiveuser:secret@localhost:5433/archivedb",
    )
    assert url == "postgresql+psycopg2://archiveuser:secret@db:5432/archivedb"


def test_resolve_alembic_url_keeps_host_localhost_when_db_also_localhost():
    url = resolve_alembic_url(
        database_url="postgresql+asyncpg://archiveuser:secret@localhost:5433/archivedb",
        alembic_database_url="postgresql+psycopg2://archiveuser:secret@localhost:5433/archivedb",
    )
    assert url == "postgresql+psycopg2://archiveuser:secret@localhost:5433/archivedb"


def test_resolve_alembic_url_derives_from_database_url_when_override_missing():
    url = resolve_alembic_url(
        database_url="postgresql+asyncpg://archiveuser:secret@db:5432/archivedb",
        alembic_database_url="",
    )
    assert url == "postgresql+psycopg2://archiveuser:secret@db:5432/archivedb"


def test_verify_schema_raises_when_users_table_missing(monkeypatch):
    class FakeInspector:
        def get_table_names(self):
            return ["documents"]

    class FakeEngine:
        def dispose(self):
            return None

    monkeypatch.setattr("sqlalchemy.create_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr("sqlalchemy.inspect", lambda engine: FakeInspector())

    with pytest.raises(RuntimeError, match="users"):
        verify_schema("postgresql+psycopg2://u:p@db:5432/archivedb")


def test_verify_schema_passes_when_required_tables_present(monkeypatch):
    class FakeInspector:
        def get_table_names(self):
            return ["users", "documents", "organizations", "alembic_version"]

    class FakeEngine:
        def dispose(self):
            return None

    monkeypatch.setattr("sqlalchemy.create_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr("sqlalchemy.inspect", lambda engine: FakeInspector())

    verify_schema("postgresql+psycopg2://u:p@db:5432/archivedb")
