import logging
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

from alembic import context

project_root = Path(__file__).parent.resolve()
sys.path.append(str(project_root))

from app.models import Base  # noqa: E402

load_dotenv()

config = context.config
logger = logging.getLogger(__name__)


def _sync_database_url(url: str) -> str:
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql+psycopg2://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg2://", 1)
    return url


def _resolve_alembic_url() -> str:
    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL не задана")

    sync_from_app = _sync_database_url(database_url)
    alembic_env = os.getenv("ALEMBIC_DATABASE_URL", "").strip()

    if not alembic_env:
        return sync_from_app

    if "+asyncpg" in alembic_env:
        raise RuntimeError(
            "ALEMBIC_DATABASE_URL должен использовать синхронный драйвер (psycopg2), без +asyncpg"
        )

    # docker compose exec api: DATABASE_URL -> @db:5432, host-only ALEMBIC URL breaks migrations
    if "@db:" in database_url and "@localhost" in alembic_env:
        logger.warning(
            "ALEMBIC_DATABASE_URL указывает на localhost, но приложение использует @db: — "
            "для миграций внутри контейнера api берётся DATABASE_URL"
        )
        return sync_from_app

    return alembic_env


alembic_url = _resolve_alembic_url()
logger.info("ALEMBIC URL (sync): %s", alembic_url.split("@")[-1] if "@" in alembic_url else alembic_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=alembic_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        render_as_batch=False,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        alembic_url,
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
