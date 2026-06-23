import os

os.environ.setdefault("SECRET_KEY", "test-secret-key-for-pytest-only-32chars!")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
