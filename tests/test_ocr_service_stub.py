"""Lightweight tests for the OCR sidecar stub (no Docker required)."""

from __future__ import annotations

import io
import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

OCR_DIR = Path(__file__).resolve().parents[1] / "ocr"
sys.path.insert(0, str(OCR_DIR))

from main import PIPELINE_VERSION, app  # noqa: E402


client = TestClient(app)


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    assert resp.json()["pipeline_version"] == PIPELINE_VERSION


def test_extract_image_format(tmp_path, monkeypatch):
    monkeypatch.setenv("UPLOADS_DIR", str(tmp_path))
    # Re-import path resolution uses module-level UPLOADS_DIR — patch it
    import main as ocr_main

    monkeypatch.setattr(ocr_main, "UPLOADS_DIR", str(tmp_path))

    img = Image.new("RGB", (2480, 3508), color=(255, 255, 255))
    # 300 DPI A4 ≈ 2480x3508
    path = tmp_path / "sheet.png"
    img.save(path, dpi=(300, 300))

    resp = client.post(
        "/v1/extract",
        json={"job_id": 1, "file_path": str(path), "original_filename": "sheet.png"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["pipeline_version"] == PIPELINE_VERSION
    assert data["geometry"]["format_from_dims"] == "A4"
    assert data["fields"]["document_format"]["value"] == "A4"
    assert data["fields"]["developed_by"]["value"] is None


def test_extract_rejects_path_outside_uploads(tmp_path, monkeypatch):
    import main as ocr_main

    monkeypatch.setattr(ocr_main, "UPLOADS_DIR", str(tmp_path))
    outside = Path("/tmp/not-in-uploads.png")
    resp = client.post(
        "/v1/extract",
        json={"job_id": 1, "file_path": str(outside)},
    )
    assert resp.status_code in (400, 404)
