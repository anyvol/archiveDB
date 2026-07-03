"""Async SMTP mailer with DB-stored configuration."""

from __future__ import annotations

import logging
import ssl
from email.message import EmailMessage
from typing import Any

import aiosmtplib
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import SMTP_FROM, SMTP_HOST, SMTP_PASSWORD, SMTP_PORT, SMTP_USE_TLS, SMTP_USER
from app.crypto_utils import decrypt_secret
from app.settings_store import get_smtp_config

logger = logging.getLogger(__name__)


def _tls_context(verify_cert: bool) -> ssl.SSLContext:
    if verify_cert:
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _env_smtp_config() -> dict[str, Any]:
    return {
        "host": SMTP_HOST,
        "port": SMTP_PORT,
        "user": SMTP_USER,
        "password": SMTP_PASSWORD,
        "from_address": SMTP_FROM,
        "use_tls": SMTP_USE_TLS,
    }


async def resolve_smtp_config(session: AsyncSession | None) -> dict[str, Any]:
    db_config: dict[str, Any] = {}
    if session is not None:
        db_config = await get_smtp_config(session)

    host = (db_config.get("host") or SMTP_HOST or "").strip()
    if not host:
        return {}

    password = db_config.get("password_encrypted") or ""
    if password:
        password = decrypt_secret(password)
    elif SMTP_PASSWORD:
        password = SMTP_PASSWORD

    return {
        "host": host,
        "port": int(db_config.get("port") or SMTP_PORT or 587),
        "user": (db_config.get("user") or SMTP_USER or "").strip(),
        "password": password,
        "from_address": (db_config.get("from_address") or SMTP_FROM or SMTP_USER or "").strip(),
        "use_tls": bool(db_config["use_tls"]) if "use_tls" in db_config else SMTP_USE_TLS,
        "tls_verify": bool(db_config["tls_verify"]) if "tls_verify" in db_config else True,
    }


async def smtp_configured(session: AsyncSession | None) -> bool:
    config = await resolve_smtp_config(session)
    return bool(config.get("host") and config.get("from_address"))


async def send_email(
    session: AsyncSession | None,
    to_address: str,
    subject: str,
    body_text: str,
    body_html: str | None = None,
) -> None:
    config = await resolve_smtp_config(session)
    if not config.get("host"):
        raise RuntimeError("SMTP is not configured")

    message = EmailMessage()
    message["From"] = config["from_address"]
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body_text)
    if body_html:
        message.add_alternative(body_html, subtype="html")

    use_tls = bool(config.get("use_tls"))
    tls_verify = bool(config.get("tls_verify", True))
    port = int(config.get("port") or 25)
    username = config.get("user") or None
    password = config.get("password") or None
    hostname = config["host"]

    # aiosmtplib auto-upgrades to STARTTLS when start_tls=None and server supports it —
    # must pass start_tls=False explicitly for Outlook-style plain port 25.
    if use_tls and port == 465:
        implicit_tls = True
        start_tls_on_connect = False
    elif use_tls:
        implicit_tls = False
        start_tls_on_connect = True
    else:
        implicit_tls = False
        start_tls_on_connect = False

    tls_context = _tls_context(tls_verify) if (implicit_tls or start_tls_on_connect) else None

    client = aiosmtplib.SMTP(
        hostname=hostname,
        port=port,
        use_tls=implicit_tls,
        start_tls=start_tls_on_connect,
        timeout=30,
        tls_context=tls_context,
    )
    await client.connect()
    try:
        if username and password:
            await client.login(username, password)
        await client.send_message(message)
    finally:
        try:
            await client.quit()
        except Exception:
            pass

    logger.info(
        "Email sent to %s via %s:%s (tls=%s, start_tls=%s)",
        to_address,
        hostname,
        port,
        use_tls,
        start_tls_on_connect,
    )
