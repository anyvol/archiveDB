"""Tests for backup history sync helpers."""

from __future__ import annotations

from datetime import datetime

from app.admin.services.backups import _parse_created_at


def test_parse_created_at_from_iso():
    item = {"created_at": "2026-07-10T12:00:00Z", "backup_id": "x"}
    assert _parse_created_at(item) == datetime(2026, 7, 10, 12, 0, 0)


def test_parse_created_at_from_backup_id():
    item = {"backup_id": "2026-07-10_120000_db"}
    assert _parse_created_at(item) == datetime(2026, 7, 10, 12, 0, 0)
