"""Run Alembic migrations against the application database."""

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config
from dotenv import load_dotenv

from app.migration_config import (
    list_db_tables,
    repair_orphaned_enums,
    repair_stale_migration_state,
    resolve_alembic_url,
    verify_schema,
)

load_dotenv()


def _config() -> Config:
    ini_path = Path(__file__).resolve().parent / "alembic.ini"
    cfg = Config(str(ini_path))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent / "alembic"))
    cfg.set_main_option("sqlalchemy.url", resolve_alembic_url())
    return cfg


def _upgrade(cfg: Config, revision: str) -> None:
    print(f"DB tables before upgrade: {list_db_tables() or ['(none)']}")
    if repair_orphaned_enums():
        print("Removed orphaned enum types from a previous failed migration.")
    if repair_stale_migration_state():
        print("Re-applying migrations after clearing stale alembic_version.")
    command.upgrade(cfg, revision)
    print(f"DB tables after upgrade: {list_db_tables() or ['(none)']}")


def main() -> None:
    args = sys.argv[1:]
    cfg = _config()

    if not args or args[0] == "upgrade":
        revision = args[1] if len(args) > 1 else "head"
        print(f"Applying migrations up to: {revision}")
        print(f"Database URL host: {resolve_alembic_url().split('@')[-1]}")
        _upgrade(cfg, revision)
        try:
            verify_schema()
        except RuntimeError:
            if repair_stale_migration_state():
                print("Schema still incomplete; retrying upgrade once more.")
                _upgrade(cfg, revision)
                verify_schema()
            else:
                raise
        print("Migrations applied and schema verified.")
        return

    if args[0] == "repair":
        if repair_stale_migration_state():
            print("Stale alembic_version cleared.")
        else:
            print("No repair needed.")
        return

    if args[0] == "verify":
        verify_schema()
        print("Schema verified.")
        return

    command.upgrade(cfg, "head")
    verify_schema()


if __name__ == "__main__":
    main()
