"""OCR sidecar for archiveDB — phase 1B stamp cell OCR."""

from __future__ import annotations

import logging
import os

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from pipeline.extract import PIPELINE_VERSION, run_extract
from pipeline.extract_cells import default_template_cells, run_extract_cells
from pipeline.ocr_engine import engine_name
from pipeline.stamp import CELL_TEMPLATE_FORM1

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ocr-service")

TOKEN = os.getenv("OCR_SERVICE_TOKEN", "").strip()
UPLOADS_DIR = os.getenv("UPLOADS_DIR", "/uploads")

app = FastAPI(title="archiveDB ocr-service", version=PIPELINE_VERSION)
security = HTTPBearer(auto_error=False)


def _auth(credentials: HTTPAuthorizationCredentials | None = Depends(security)) -> None:
    if not TOKEN:
        return
    if credentials is None or credentials.credentials != TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


def _resolve_path(file_path: str) -> str:
    """Resolve a path under UPLOADS_DIR."""
    uploads_root = os.path.normpath(UPLOADS_DIR)
    raw = (file_path or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="file_path is required")

    if os.path.isabs(raw):
        full = os.path.normpath(raw)
        marker = f"{os.sep}uploaded_files{os.sep}"
        if marker in full and not (full == uploads_root or full.startswith(uploads_root + os.sep)):
            rel = full.split(marker, 1)[1]
            full = os.path.normpath(os.path.join(uploads_root, rel))
    else:
        full = os.path.normpath(os.path.join(uploads_root, raw))

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
    # Optional overrides from format-bound templates / human stamp annotation
    stamp_roi_norm: list[float] | None = None
    cells: list[CellBox] | None = None
    document_format_hint: str | None = None


class CellBox(BaseModel):
    key: str
    bbox_norm: list[float]
    category: str | None = None
    text: str | None = None


class ExtractCellsRequest(BaseModel):
    job_id: int
    stamp_crop_path: str
    cells: list[CellBox]


class ExtractResponse(BaseModel):
    pipeline_version: str = PIPELINE_VERSION
    fields: dict = Field(default_factory=dict)
    geometry: dict = Field(default_factory=dict)
    stamp_crop_path: str | None = None
    page_preview_path: str | None = None
    person_suggestions: dict = Field(default_factory=dict)


@app.get("/health")
def health() -> dict[str, str]:
    from pipeline.detector import detector_status

    status = {
        "status": "ok",
        "pipeline_version": PIPELINE_VERSION,
        "engine": engine_name(),
        "render_dpi": str(os.getenv("OCR_RENDER_DPI", "400")),
    }
    det = detector_status()
    status["stamp_detector"] = "on" if det.get("enabled") else "off"
    return status


@app.get("/v1/version")
def version(_: None = Depends(_auth)) -> dict[str, str]:
    return {"pipeline_version": PIPELINE_VERSION, "engine": engine_name()}


@app.get("/v1/field-keys")
def field_keys(_: None = Depends(_auth)) -> dict:
    return {
        "keys": [
            {"key": spec.key, "category": spec.whitelist or spec.key, "bbox_norm": list(spec.box)}
            for spec in CELL_TEMPLATE_FORM1
        ],
        "default_cells": default_template_cells(),
    }


@app.post("/v1/extract", response_model=ExtractResponse)
def extract(body: ExtractRequest, _: None = Depends(_auth)) -> ExtractResponse:
    full_path = _resolve_path(body.file_path)
    try:
        result = run_extract(
            job_id=body.job_id,
            full_path=full_path,
            uploads_dir=UPLOADS_DIR,
            original_filename=body.original_filename,
            stamp_roi_norm=body.stamp_roi_norm,
            cells=[c.model_dump() for c in body.cells] if body.cells else None,
            document_format_hint=body.document_format_hint,
        )
    except Exception as exc:
        logger.exception("extract failed job_id=%s", body.job_id)
        raise HTTPException(status_code=500, detail=f"extract failed: {exc}") from exc
    return ExtractResponse(**result)


@app.post("/v1/extract-cells", response_model=ExtractResponse)
def extract_cells(body: ExtractCellsRequest, _: None = Depends(_auth)) -> ExtractResponse:
    stamp_path = _resolve_path(body.stamp_crop_path)
    try:
        result = run_extract_cells(
            job_id=body.job_id,
            stamp_path=stamp_path,
            cells=[c.model_dump() for c in body.cells],
            pipeline_version=PIPELINE_VERSION,
        )
    except Exception as exc:
        logger.exception("extract-cells failed job_id=%s", body.job_id)
        raise HTTPException(status_code=500, detail=f"extract-cells failed: {exc}") from exc
    return ExtractResponse(**result)
