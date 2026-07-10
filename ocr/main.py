"""OCR sidecar for archiveDB — phase 1A stub (format-by-dimensions, empty stamp fields)."""

from __future__ import annotations

import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from format_detect import detect_format_from_file

PIPELINE_VERSION = "stub-1.0"
TOKEN = os.getenv("OCR_SERVICE_TOKEN", "").strip()
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/uploads")

app = FastAPI(title="archiveDB ocr-service", version=PIPELINE_VERSION)
security = HTTPBearer(auto_error=False)

_EMPTY_FIELD_KEYS = (
    "designation",
    "doc_name",
    "developed_by",
    "reviewed_by",
    "approved_by",
    "developer_signed_date",
    "reviewer_signed_date",
    "approver_signed_date",
    "document_format",
    "scale",
    "sheet",
    "sheets_total",
)


def _auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if not TOKEN:
        return
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _empty_field() -> dict[str, Any]:
    return {"raw": None, "value": None, "conf": None, "bbox": None, "page": 0}


def _resolve_path(file_path: str) -> str:
    """Allow absolute paths under UPLOADS_DIR or paths relative to UPLOADS_DIR."""
    if os.path.isabs(file_path):
        full = os.path.normpath(file_path)
    else:
        full = os.path.normpath(os.path.join(UPLOADS_DIR, file_path))
    uploads_root = os.path.normpath(UPLOADS_DIR)
    if not (full == uploads_root or full.startswith(uploads_root + os.sep)):
        raise HTTPException(status_code=400, detail="file_path outside uploads directory")
    if not os.path.isfile(full):
        raise HTTPException(status_code=404, detail="File not found")
    return full


class ExtractRequest(BaseModel):
    job_id: int
    file_path: str
    mime: str | None = None
    original_filename: str | None = None


class ExtractResponse(BaseModel):
    pipeline_version: str = PIPELINE_VERSION
    fields: dict[str, Any] = Field(default_factory=dict)
    geometry: dict[str, Any] = Field(default_factory=dict)
    stamp_crop_path: str | None = None
    page_preview_path: str | None = None
    person_suggestions: dict[str, Any] = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "pipeline_version": PIPELINE_VERSION}


@app.get("/v1/version")
def version(_: None = Depends(_auth)) -> dict[str, str]:
    return {"pipeline_version": PIPELINE_VERSION}


@app.post("/v1/extract", response_model=ExtractResponse)
def extract(body: ExtractRequest, _: None = Depends(_auth)) -> ExtractResponse:
    """Stub extract: detect sheet format from dimensions; stamp fields stay empty until phase 1B."""
    full_path = _resolve_path(body.file_path)
    format_code, page_count = detect_format_from_file(full_path)

    fields = {key: _empty_field() for key in _EMPTY_FIELD_KEYS}
    if format_code:
        fields["document_format"] = {
            "raw": format_code,
            "value": format_code,
            "conf": 0.9,
            "bbox": None,
            "page": 0,
        }

    return ExtractResponse(
        pipeline_version=PIPELINE_VERSION,
        fields=fields,
        geometry={
            "format_from_dims": format_code,
            "format_from_ocr": None,
            "page_count": page_count,
            "stamp_roi": None,
            "job_id": body.job_id,
        },
        stamp_crop_path=None,
        page_preview_path=None,
        person_suggestions={},
    )
