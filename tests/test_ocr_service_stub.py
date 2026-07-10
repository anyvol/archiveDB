"""Lightweight tests for the OCR sidecar (phase 1B pipeline modules)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient
from PIL import Image

OCR_DIR = Path(__file__).resolve().parents[1] / "ocr"
sys.path.insert(0, str(OCR_DIR))

from main import PIPELINE_VERSION, app  # noqa: E402
from pipeline.stamp import CELL_TEMPLATE_FORM1, crop_norm, extract_stamp  # noqa: E402


client = TestClient(app)


def test_health_reports_engine():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["pipeline_version"] == PIPELINE_VERSION
    assert data["engine"] in {"tesseract", "paddleocr"}


def test_stamp_roi_and_cells():
    page = np.zeros((1000, 1400, 3), dtype=np.uint8)
    page[:] = 255
    stamp, bbox, meta = extract_stamp(page)
    assert stamp.shape[0] > 10 and stamp.shape[1] > 10
    assert meta["template"].startswith("gost")
    assert len(CELL_TEMPLATE_FORM1) >= 8
    cell, local = crop_norm(stamp, CELL_TEMPLATE_FORM1[0].box)
    assert cell.size > 0
    assert local[2] > local[0]


def test_extract_image_creates_fields(tmp_path, monkeypatch):
    import main as ocr_main

    monkeypatch.setattr(ocr_main, "UPLOADS_DIR", str(tmp_path))
    img = Image.new("RGB", (2480, 3508), color=(255, 255, 255))
    path = tmp_path / "sheet.png"
    img.save(path, dpi=(300, 300))

    resp = client.post(
        "/v1/extract",
        json={"job_id": 42, "file_path": str(path), "original_filename": "sheet.png"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_version"] == PIPELINE_VERSION
    assert "designation" in data["fields"]
    assert data["geometry"]["format_from_dims"] == "A4"
    assert data["geometry"]["engine"] in {"tesseract", "paddleocr"}
    assert data["stamp_crop_path"]
    stamp_abs = tmp_path / data["stamp_crop_path"]
    assert stamp_abs.is_file()
