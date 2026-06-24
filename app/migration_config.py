import os


def resolve_alembic_url(database_url: str | None = None, alembic_database_url: str | None = None) -> str:
    """Build sync Alembic URL from async DATABASE_URL and optional host override."""
    database_url = database_url or os.getenv("DATABASE_URL", "")
    if not database_url:
        raise RuntimeError("DATABASE_URL не задана")

    derived = database_url.replace("+asyncpg", "+psycopg2")
    explicit = alembic_database_url if alembic_database_url is not None else os.getenv("ALEMBIC_DATABASE_URL")
    if not explicit:
        return derived
    if "+asyncpg" in explicit:
        raise RuntimeError("ALEMBIC_DATABASE_URL должен использовать синхронный драйвер (psycopg2), без +asyncpg")
    if ("@localhost" in explicit or "@127.0.0.1" in explicit) and "@db:" in database_url:
        return derived
    return explicit
