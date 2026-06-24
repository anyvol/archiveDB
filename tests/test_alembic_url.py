from app.migration_config import resolve_alembic_url


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
