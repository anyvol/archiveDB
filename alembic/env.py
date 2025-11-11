import os
from logging.config import fileConfig
import logging

from sqlalchemy import pool
from sqlalchemy import create_engine  # Синхронный engine

from alembic import context
from app.models import Base

import sys
from pathlib import Path

# Добавляем путь к проекту
project_root = Path(__file__).parent.resolve()
sys.path.append(str(project_root))

# Загружаем модели (импорт один раз)
from app.models import Base

# Загружаем .env
from dotenv import load_dotenv
load_dotenv()

# Инициализируем config
config = context.config

# Настройка URL БД
DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL не задана")

# URL для Alembic (синхронный драйвер для всех операций)
alembic_url = os.getenv("ALEMBIC_DATABASE_URL", DATABASE_URL.replace("+asyncpg", ""))
if "+asyncpg" in alembic_url:
    raise RuntimeError("ALEMBIC_DATABASE_URL должен использовать синхронный драйвер (psycopg2), без +asyncpg")

config.set_main_option("sqlalchemy.url", alembic_url)

logger = logging.getLogger(__name__)
logger.info(f"ALEMBIC URL (sync): {alembic_url}")
logger.info(f"DATABASE_URL (original): {DATABASE_URL}")

# Конфигурация логирования
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Проверка, что модели импортированы
print(f"✅ Загружены таблицы: {list(Base.metadata.tables.keys())}")
target_metadata = Base.metadata

def run_migrations_offline():
    """Запуск миграций в оффлайн-режиме (синхронный)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection):
    """Функция для выполнения миграций внутри синхронного контекста."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,  # Сравнение типов колонок
        render_as_batch=False,  # Включить для SQLite
    )

    with context.begin_transaction():
        context.run_migrations()

def run_migrations_online():
    """Запуск миграций в онлайн-режиме (синхронный для теста)."""
    # Создаём синхронный движок
    connectable = create_engine(
        alembic_url,  # Используем синхронный URL
        poolclass=pool.NullPool,
        echo=True,  # Включить для отладки SQL
    )

    with connectable.connect() as connection:
        do_run_migrations(connection)

    connectable.dispose()

def main():
    """Основная функция запуска миграций."""
    if context.is_offline_mode():
        run_migrations_offline()
    else:
        run_migrations_online()

if __name__ == "__main__":
    main()
