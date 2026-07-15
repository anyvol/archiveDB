"""Background loop that sends scheduled mailing emails by cron."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.database import async_session
from app.mailing_schedule import (
    cron_matches,
    get_mailing_schedule,
    is_before_or_on_stop_date,
    save_mailing_schedule,
)
from app.admin.services.messaging import send_admin_email_to_addresses
from app.settings_store import get_app_timezone
from app.timezone_utils import resolve_timezone

logger = logging.getLogger(__name__)

_last_run_minute_key: str | None = None
_runner_task: asyncio.Task | None = None


async def run_due_mailing(now: datetime | None = None) -> bool:
    """Send scheduled mailing if enabled and cron matches. Returns True if sent."""
    global _last_run_minute_key

    async with async_session() as session:
        schedule = await get_mailing_schedule(session)
        if not schedule.enabled:
            return False
        if not schedule.addresses or not schedule.subject.strip() or not schedule.body.strip():
            return False

        tz_name = await get_app_timezone(session)
        tz = resolve_timezone(tz_name)
        moment = now or datetime.now(tz)
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=tz)
        else:
            moment = moment.astimezone(tz)

        if not is_before_or_on_stop_date(schedule, moment):
            schedule.enabled = False
            schedule.last_error = None
            await save_mailing_schedule(session, schedule)
            logger.info(
                "Scheduled mailing stopped: past stop_date=%s",
                schedule.stop_date,
            )
            return False

        if not cron_matches(schedule.cron, moment):
            return False

        minute_key = moment.strftime("%Y-%m-%d %H:%M")
        if minute_key == _last_run_minute_key or schedule.last_run_minute == minute_key:
            _last_run_minute_key = minute_key
            return False

        _last_run_minute_key = minute_key
        try:
            sent = await send_admin_email_to_addresses(
                session,
                schedule.addresses,
                schedule.subject,
                schedule.body,
                signature=schedule.signature,
            )
            schedule.last_sent_at = datetime.now(timezone.utc).isoformat()
            schedule.last_sent_count = sent
            schedule.last_error = None
            schedule.last_run_minute = minute_key
            await save_mailing_schedule(session, schedule)
            logger.info("Scheduled mailing sent to %s recipients", sent)
            return True
        except Exception as exc:
            logger.exception("Scheduled mailing failed")
            schedule.last_error = str(exc)[:300]
            schedule.last_run_minute = minute_key
            await save_mailing_schedule(session, schedule)
            return False


async def _mailing_loop() -> None:
    while True:
        try:
            await asyncio.sleep(30)
            await run_due_mailing()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled mailing loop error")


def start_mailing_runner() -> asyncio.Task:
    global _runner_task
    if _runner_task is not None and not _runner_task.done():
        return _runner_task
    _runner_task = asyncio.create_task(_mailing_loop(), name="mailing-schedule-runner")
    return _runner_task


async def stop_mailing_runner() -> None:
    global _runner_task
    if _runner_task is None:
        return
    _runner_task.cancel()
    try:
        await _runner_task
    except asyncio.CancelledError:
        pass
    _runner_task = None
