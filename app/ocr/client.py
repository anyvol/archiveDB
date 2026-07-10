"""HTTP client for the OCR sidecar — never raises into request handlers unchecked."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config import OCR_SERVICE_TIMEOUT_SEC, OCR_SERVICE_TOKEN, OCR_SERVICE_URL

logger = logging.getLogger(__name__)


class OcrServiceError(Exception):
    """OCR sidecar unavailable or returned an error."""

    def __init__(self, message: str, *, unavailable: bool = False):
        super().__init__(message)
        self.unavailable = unavailable


def _headers() -> dict[str, str]:
    if not OCR_SERVICE_TOKEN:
        return {}
    return {"Authorization": f"Bearer {OCR_SERVICE_TOKEN}"}


async def check_ocr_health() -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=min(5.0, OCR_SERVICE_TIMEOUT_SEC)) as client:
            response = await client.get(f"{OCR_SERVICE_URL}/health")
            response.raise_for_status()
            return response.json()
    except Exception as exc:
        logger.warning("OCR health check failed: %s", exc)
        return None


async def call_extract(
    *,
    job_id: int,
    file_path: str,
    mime: str | None = None,
    original_filename: str | None = None,
) -> dict[str, Any]:
    """Call POST /v1/extract. Raises OcrServiceError on transport/HTTP failures."""
    payload = {
        "job_id": job_id,
        "file_path": file_path,
        "mime": mime,
        "original_filename": original_filename,
    }
    return await _post_json("/v1/extract", payload)


async def call_extract_cells(
    *,
    job_id: int,
    stamp_crop_path: str,
    cells: list[dict[str, Any]],
) -> dict[str, Any]:
    """Call POST /v1/extract-cells with manual/annotated cell boxes."""
    payload = {
        "job_id": job_id,
        "stamp_crop_path": stamp_crop_path,
        "cells": cells,
    }
    return await _post_json("/v1/extract-cells", payload)


async def _post_json(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    try:
        async with httpx.AsyncClient(timeout=OCR_SERVICE_TIMEOUT_SEC) as client:
            response = await client.post(
                f"{OCR_SERVICE_URL}{path}",
                json=payload,
                headers=_headers(),
            )
            if response.status_code >= 500:
                raise OcrServiceError(
                    f"OCR service error {response.status_code}",
                    unavailable=True,
                )
            if response.status_code >= 400:
                detail = response.text[:300]
                raise OcrServiceError(f"OCR rejected request: {detail}")
            return response.json()
    except OcrServiceError:
        raise
    except httpx.TimeoutException as exc:
        raise OcrServiceError("OCR service timeout", unavailable=True) from exc
    except httpx.HTTPError as exc:
        raise OcrServiceError(f"OCR service unavailable: {exc}", unavailable=True) from exc
