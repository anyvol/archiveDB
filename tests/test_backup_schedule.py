from app.backup_schedule import BackupScheduleConfig, DEFAULT_BACKUP_SCHEDULE


def test_default_schedule():
    assert DEFAULT_BACKUP_SCHEDULE.enabled is False
    assert DEFAULT_BACKUP_SCHEDULE.mode == "cron"
    assert DEFAULT_BACKUP_SCHEDULE.backup_db is True


def test_normalize_schedule_from_dict():
    config = BackupScheduleConfig.model_validate(
        {
            "enabled": True,
            "mode": "interval",
            "interval_hours": 12,
            "backup_db": False,
            "backup_files": True,
        }
    )
    assert config.enabled is True
    assert config.mode == "interval"
    assert config.interval_hours == 12
    assert config.backup_db is False


def test_backup_schedule_model_validation():
    config = BackupScheduleConfig(enabled=True, cron="0 3 * * *")
    assert config.cron == "0 3 * * *"
