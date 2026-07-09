"""Tests for backup schedule retention setting."""

from app.backup_schedule import BackupScheduleConfig, DEFAULT_BACKUP_SCHEDULE


def test_default_retention_days():
    assert DEFAULT_BACKUP_SCHEDULE.retention_days == 30


def test_schedule_retention_validation():
    config = BackupScheduleConfig(enabled=True, retention_days=14)
    assert config.retention_days == 14
