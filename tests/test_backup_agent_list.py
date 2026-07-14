"""Tests for backup-agent list and retention cleanup."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

BACKUP_DIR = Path(__file__).resolve().parents[1] / "backup"
if str(BACKUP_DIR) not in sys.path:
    sys.path.insert(0, str(BACKUP_DIR))

import main as backup_main  # noqa: E402


@pytest.fixture()
def backup_root(tmp_path, monkeypatch):
    monkeypatch.setattr(backup_main, "BACKUP_DIR", tmp_path)
    monkeypatch.setattr(backup_main, "SCHEDULE_FILE", tmp_path / "schedule.json")
    return tmp_path


def _write_batch(root: Path, stamp: str, triggered_by: str = "auto-schedule") -> Path:
    batch = root / stamp
    batch.mkdir()
    payload = [
        {
            "backup_id": f"{stamp}_db",
            "backup_type": "db",
            "file_path": str(batch / "db.dump"),
            "size_bytes": 10,
            "status": "completed",
            "triggered_by": triggered_by,
        }
    ]
    (batch / "db.dump").write_bytes(b"dump")
    (batch / "manifest.json").write_text(json.dumps(payload), encoding="utf-8")
    return batch


def test_list_backups_skips_schedule_json(backup_root):
    _write_batch(backup_root, "2026-07-10_120000", triggered_by="auto-schedule")
    (backup_root / "schedule.json").write_text("{}", encoding="utf-8")

    items = backup_main._list_backups()

    assert len(items) == 1
    assert items[0]["backup_id"] == "2026-07-10_120000_db"
    assert items[0]["triggered_by"] == "auto-schedule"
    assert items[0]["created_at"].startswith("2026-07-10T12:00:00")


def test_cleanup_keeps_newest_batch_even_if_expired(backup_root):
    old = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d_%H%M%S")
    newest = (datetime.utcnow() - timedelta(days=9)).strftime("%Y-%m-%d_%H%M%S")
    _write_batch(backup_root, old)
    _write_batch(backup_root, newest)

    backup_main._cleanup_old_backups({"retention_days": 1})

    remaining = [p.name for p in backup_root.iterdir() if p.is_dir()]
    assert remaining == [newest]


def test_cleanup_deletes_expired_but_keeps_fresh(backup_root):
    old = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d_%H%M%S")
    fresh = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
    _write_batch(backup_root, old)
    _write_batch(backup_root, fresh)

    backup_main._cleanup_old_backups({"retention_days": 7})

    remaining = sorted(p.name for p in backup_root.iterdir() if p.is_dir())
    assert remaining == [fresh]
