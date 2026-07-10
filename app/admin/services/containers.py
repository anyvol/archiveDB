"""HTTP client for the ops-agent sidecar."""

from __future__ import annotations

import logging

import httpx

from app.config import OPS_AGENT_TOKEN, OPS_AGENT_URL

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    if not OPS_AGENT_TOKEN:
        return {}
    return {"Authorization": f"Bearer {OPS_AGENT_TOKEN}"}


async def fetch_containers() -> list[dict]:
    if not OPS_AGENT_URL:
        return []
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{OPS_AGENT_URL}/containers", headers=_headers())
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("ops-agent containers request failed: %s", exc)
        return []


async def fetch_container_logs(name: str, tail: int = 200) -> str:
    if not OPS_AGENT_URL:
        return "ops-agent не настроен."
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{OPS_AGENT_URL}/containers/{name}/logs",
                params={"tail": tail},
                headers=_headers(),
            )
            response.raise_for_status()
            data = response.json()
            return data.get("logs", "")
    except Exception as exc:
        return f"Не удалось получить логи: {exc}"
