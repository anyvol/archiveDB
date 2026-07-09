"""Administration panel routes (master_admin only)."""

from __future__ import annotations

import logging
from datetime import datetime

from urllib.parse import quote

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.auth import get_current_user_from_token
from app.config import SERVICE_VERSION, url_path
from app.crypto_utils import encrypt_secret
from app.database import get_session
from app.mail.sender import send_email, smtp_configured, resolve_smtp_config
from app.models import BackupRecord, User, UserRole, USER_ROLE_LABELS, DEPARTMENTS
from app.notifications import count_unread
from app.permissions import is_master_admin
from app.admin.services.users import delete_user_account
from app.admin.services.messaging import send_admin_email_to_user, send_admin_email_to_all
from app.admin_access import issue_admin_access_code
from app.settings_store import (
    SETTING_APP_TIMEZONE,
    SETTING_SMTP,
    get_app_timezone,
    get_smtp_config,
    set_setting,
)
from app.role_permissions import (
    CONFIGURABLE_ROLES,
    PERMISSION_DEFINITIONS,
    get_cached_role_permissions,
    load_role_permissions,
    save_role_permissions,
)
from app.backup_schedule import BackupScheduleConfig, get_backup_schedule, save_backup_schedule
from app.timezone_utils import common_timezones, format_datetime
from app.admin.services.backups import (
    apply_remote_backup_schedule,
    backup_host_path_display,
    list_remote_backups,
    sync_backup_records,
    trigger_backup,
)
from app.admin.services.containers import fetch_container_logs, fetch_containers
from app.admin.services.traffic import collect_traffic_stats, format_bytes

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="templates")
templates.env.globals["url_path"] = url_path
templates.env.globals["is_master_admin"] = is_master_admin
templates.env.globals["UserRole"] = UserRole
templates.env.globals["USER_ROLE_LABELS"] = USER_ROLE_LABELS
templates.env.globals["DEPARTMENTS"] = DEPARTMENTS


def _see_other(url: str) -> RedirectResponse:
    """POST/redirect/GET — avoid 307 which re-submits POST and causes redirect loops."""
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def _smtp_host_error(host: str) -> str | None:
    host = host.strip()
    if not host or "@" in host or " " in host:
        return "host"
    return None

async def _admin_context(session: AsyncSession, user: User, nav: str) -> dict:
    return {
        "user": user,
        "unread_count": await count_unread(session, user.id),
        "nav_context": "admin",
        "admin_nav": nav,
        "service_version": SERVICE_VERSION,
        "USER_ROLE_LABELS": USER_ROLE_LABELS,
        "DEPARTMENTS": DEPARTMENTS,
        "UserRole": UserRole,
        "url_path": url_path,
    }


async def _require_master_admin_page(
    access_token: str | None,
    session: AsyncSession,
) -> User:
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    user = await get_current_user_from_token(access_token=access_token, db=session)
    if not is_master_admin(user):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    stats = await collect_traffic_stats(session)
    containers = await fetch_containers()
    mailer_ok = await smtp_configured(session)
    ctx = await _admin_context(session, user, "dashboard")
    return templates.TemplateResponse(
        "admin/index.html",
        {
            "request": request,
            "stats": stats,
            "format_bytes": format_bytes,
            "containers": containers,
            "mailer_ok": mailer_ok,
            "timezone": await get_app_timezone(session),
            **ctx,
        },
    )


@router.get("/containers", response_class=HTMLResponse)
async def admin_containers(
    request: Request,
    name: str | None = Query(None),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    containers = await fetch_containers()
    selected = name or (containers[0]["name"] if containers else None)
    logs = await fetch_container_logs(selected) if selected else ""
    ctx = await _admin_context(session, user, "containers")
    return templates.TemplateResponse(
        "admin/containers.html",
        {
            "request": request,
            "containers": containers,
            "selected": selected,
            "logs": logs,
            **ctx,
        },
    )


@router.get("/users", response_class=HTMLResponse)
async def admin_users(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    result = await session.execute(select(User).order_by(User.login))
    users = result.scalars().all()
    ctx = await _admin_context(session, user, "users")
    return templates.TemplateResponse(
        "admin/users.html",
        {
            "request": request,
            "users": users,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            **ctx,
        },
    )


@router.post("/users/broadcast-email")
async def admin_broadcast_email(
    subject: str = Form(...),
    body: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    try:
        sent = await send_admin_email_to_all(session, subject, body)
    except Exception as exc:
        logger.exception("Admin broadcast email failed")
        return _see_other(url_path(f"/admin/users?error={quote(str(exc)[:120])}"))
    return _see_other(url_path(f"/admin/users?success=broadcast&count={sent}"))


@router.post("/users/{user_id}")
async def admin_update_user(
    user_id: int,
    role: str = Form(...),
    is_active: str = Form("false"),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        actor = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalars().first()
    if target is None:
        return RedirectResponse(url=url_path("/admin/users?error=not_found"))

    try:
        new_role = UserRole(role)
    except ValueError:
        return RedirectResponse(url=url_path("/admin/users?error=role"))

    if new_role == UserRole.master_admin and actor.id != target.id:
        return RedirectResponse(url=url_path("/admin/users?error=master_admin"))

    if target.role == UserRole.master_admin and new_role != UserRole.master_admin:
        return RedirectResponse(url=url_path("/admin/users?error=master_admin"))

    target.role = new_role
    target.is_active = is_active == "true"
    if new_role != UserRole.user:
        target.access_granted = True
    await session.commit()
    return _see_other(url_path("/admin/users?success=1"))


@router.post("/users/{user_id}/delete")
async def admin_delete_user(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        actor = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalars().first()
    if target is None:
        return _see_other(url_path("/admin/users?error=not_found"))
    try:
        await delete_user_account(session, actor, target)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "delete_failed"
        return _see_other(url_path(f"/admin/users?error={detail}"))
    return _see_other(url_path("/admin/users?success=deleted"))


@router.post("/users/{user_id}/access-code")
async def admin_issue_access_code(
    user_id: int,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        actor = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalars().first()
    if target is None:
        return _see_other(url_path("/admin/users?error=not_found"))
    try:
        code = await issue_admin_access_code(session, target, created_by_id=actor.id)
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else "access_code"
        return _see_other(url_path(f"/admin/users?error={quote(str(detail))}"))
    return _see_other(
        url_path(
            f"/admin/users?success=access_code&for_login={quote(target.login)}&code={code}"
        )
    )


@router.post("/users/{user_id}/email")
async def admin_email_user(
    user_id: int,
    subject: str = Form(...),
    body: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    result = await session.execute(select(User).where(User.id == user_id))
    target = result.scalars().first()
    if target is None:
        return _see_other(url_path("/admin/users?error=not_found"))
    try:
        await send_admin_email_to_user(session, target, subject, body)
    except Exception as exc:
        logger.exception("Admin email to user failed")
        return _see_other(url_path(f"/admin/users?error={quote(str(exc)[:120])}"))
    return _see_other(url_path(f"/admin/users?success=email_sent&for_login={quote(target.login)}"))


@router.get("/traffic", response_class=HTMLResponse)
async def admin_traffic(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    stats = await collect_traffic_stats(session)
    ctx = await _admin_context(session, user, "traffic")
    return templates.TemplateResponse(
        "admin/traffic.html",
        {"request": request, "stats": stats, "format_bytes": format_bytes, **ctx},
    )


@router.get("/timezone", response_class=HTMLResponse)
async def admin_timezone_page(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    tz = await get_app_timezone(session)
    ctx = await _admin_context(session, user, "timezone")
    return templates.TemplateResponse(
        "admin/timezone.html",
        {
            "request": request,
            "timezone": tz,
            "timezones": common_timezones(),
            "now_formatted": format_datetime(datetime.utcnow(), tz),
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            **ctx,
        },
    )


@router.post("/timezone")
async def admin_timezone_save(
    timezone: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    if timezone not in common_timezones():
        return RedirectResponse(url=url_path("/admin/timezone?error=invalid"))

    await set_setting(session, SETTING_APP_TIMEZONE, timezone, updated_by_id=user.id)
    try:
        await session.execute(text(f"ALTER DATABASE archivedb SET timezone TO '{timezone}'"))
        await session.commit()
    except Exception:
        logger.exception("Failed to set PostgreSQL timezone")

    return _see_other(url_path("/admin/timezone?success=1"))


@router.get("/backups", response_class=HTMLResponse)
async def admin_backups(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    remote = await list_remote_backups()
    await sync_backup_records(session, remote)
    result = await session.execute(select(BackupRecord).order_by(BackupRecord.created_at.desc()))
    records = result.scalars().all()
    schedule = await get_backup_schedule(session)
    ctx = await _admin_context(session, user, "backups")
    return templates.TemplateResponse(
        "admin/backups.html",
        {
            "request": request,
            "records": records,
            "backup_host_path": backup_host_path_display(),
            "format_bytes": format_bytes,
            "format_datetime": format_datetime,
            "timezone": await get_app_timezone(session),
            "schedule": schedule,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            **ctx,
        },
    )


@router.get("/backups/list")
async def admin_backups_list_json(
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        raise HTTPException(status_code=401, detail="Не авторизован")
    try:
        await _require_master_admin_page(access_token, session)
    except HTTPException:
        raise HTTPException(status_code=403, detail="Недостаточно прав")

    remote = await list_remote_backups()
    await sync_backup_records(session, remote)
    result = await session.execute(select(BackupRecord).order_by(BackupRecord.created_at.desc()))
    records = result.scalars().all()
    tz = await get_app_timezone(session)
    return {
        "records": [
            {
                "backup_id": r.backup_id,
                "backup_type": r.backup_type,
                "size_bytes_display": format_bytes(r.size_bytes or 0),
                "status": r.status,
                "created_at_display": format_datetime(r.created_at, tz),
                "triggered_by": r.triggered_by,
            }
            for r in records
        ]
    }


@router.post("/backups/run")
async def admin_run_backup(
    backup_db: str = Form("false"),
    backup_files: str = Form("false"),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    types: list[str] = []
    if backup_db == "true":
        types.append("db")
    if backup_files == "true":
        types.append("files")
    if not types:
        return _see_other(url_path("/admin/backups?error=types"))

    try:
        result = await trigger_backup(types, triggered_by=user.login)
        await sync_backup_records(session, result.get("results", []))
    except Exception:
        logger.exception("Backup failed")
        return _see_other(url_path("/admin/backups?error=run"))
    return _see_other(url_path("/admin/backups?success=1"))


@router.post("/backups/schedule")
async def admin_save_backup_schedule(
    enabled: str = Form("false"),
    mode: str = Form("cron"),
    cron: str = Form("0 2 * * *"),
    interval_hours: int = Form(24),
    backup_db: str = Form("false"),
    backup_files: str = Form("false"),
    retention_days: int = Form(30),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    if mode not in ("cron", "interval"):
        return _see_other(url_path("/admin/backups?error=schedule_mode"))

    config = BackupScheduleConfig(
        enabled=enabled == "true",
        mode=mode,  # type: ignore[arg-type]
        cron=cron.strip() or "0 2 * * *",
        interval_hours=max(1, min(interval_hours, 168)),
        backup_db=backup_db == "true",
        backup_files=backup_files == "true",
        retention_days=max(1, min(retention_days, 365)),
    )
    if config.enabled and not config.backup_db and not config.backup_files:
        return _see_other(url_path("/admin/backups?error=schedule_types"))

    await save_backup_schedule(session, config, updated_by_id=user.id)
    try:
        await apply_remote_backup_schedule(config.model_dump())
    except Exception:
        logger.exception("Failed to apply backup schedule to agent")
        return _see_other(url_path("/admin/backups?error=schedule_apply"))
    return _see_other(url_path("/admin/backups?success=schedule"))


@router.get("/permissions", response_class=HTMLResponse)
async def admin_permissions(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    matrix = await load_role_permissions(session)
    ctx = await _admin_context(session, user, "permissions")
    return templates.TemplateResponse(
        "admin/permissions.html",
        {
            "request": request,
            "permissions": PERMISSION_DEFINITIONS,
            "roles": CONFIGURABLE_ROLES,
            "matrix": matrix,
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            **ctx,
        },
    )


@router.post("/permissions")
async def admin_permissions_save(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    form = await request.form()
    matrix = get_cached_role_permissions()
    updated: dict[str, dict[str, bool]] = {}
    for role in CONFIGURABLE_ROLES:
        role_key = role.value
        updated[role_key] = {}
        for perm in PERMISSION_DEFINITIONS:
            key = perm["key"]
            updated[role_key][key] = f"perm_{role_key}_{key}" in form

    await save_role_permissions(session, updated, updated_by_id=user.id)
    return _see_other(url_path("/admin/permissions?success=1"))


@router.get("/mailer", response_class=HTMLResponse)
async def admin_mailer(
    request: Request,
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        user = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    smtp = await get_smtp_config(session)
    resolved = await resolve_smtp_config(session)
    ctx = await _admin_context(session, user, "mailer")
    return templates.TemplateResponse(
        "admin/mailer.html",
        {
            "request": request,
            "smtp": smtp,
            "resolved": resolved,
            "configured": await smtp_configured(session),
            "success": request.query_params.get("success"),
            "error": request.query_params.get("error"),
            "error_detail": request.query_params.get("detail"),
            **ctx,
        },
    )


@router.post("/mailer")
async def admin_mailer_save(
    host: str = Form(...),
    port: int = Form(25),
    user: str = Form(""),
    password: str = Form(""),
    from_address: str = Form(...),
    use_tls: str = Form(""),
    tls_verify: str = Form(""),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        actor = await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    host = host.strip()
    if err := _smtp_host_error(host):
        return _see_other(url_path(f"/admin/mailer?error={err}"))

    existing = await get_smtp_config(session)
    if not password.strip() and not existing.get("password_encrypted"):
        return _see_other(url_path("/admin/mailer?error=password"))

    payload = {
        "host": host,
        "port": port,
        "user": user.strip(),
        "from_address": from_address.strip(),
        "use_tls": use_tls == "true",
        "tls_verify": tls_verify == "true",
        "password_encrypted": existing.get("password_encrypted", ""),
    }
    if password.strip():
        payload["password_encrypted"] = encrypt_secret(password.strip())

    await set_setting(session, SETTING_SMTP, payload, updated_by_id=actor.id)
    return _see_other(url_path("/admin/mailer?success=1"))


@router.post("/mailer/test")
async def admin_mailer_test(
    test_email: str = Form(...),
    session: AsyncSession = Depends(get_session),
    access_token: str | None = Cookie(None),
):
    if not access_token:
        return RedirectResponse(url=url_path("/login"))
    try:
        await _require_master_admin_page(access_token, session)
    except HTTPException:
        return RedirectResponse(url=url_path("/documents"))

    try:
        config = await resolve_smtp_config(session)
        if "@" in (config.get("host") or ""):
            return _see_other(url_path("/admin/mailer?error=test_host"))
        await send_email(
            session,
            to_address=test_email.strip(),
            subject="archiveDB — тестовое письмо",
            body_text="Почтовый сервер archiveDB настроен корректно.",
        )
    except Exception as exc:
        logger.exception("Test email failed")
        detail = quote(str(exc)[:200])
        return _see_other(url_path(f"/admin/mailer?error=test_connect&detail={detail}"))
    return _see_other(url_path("/admin/mailer?success=test"))
