"""Tests for extract-cells path in OCR sidecar."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image

from sidecar_import import load_sidecar

OCR_DIR = Path(__file__).resolve().parents[1] / "ocr"
if str(OCR_DIR) not in sys.path:
    sys.path.insert(0, str(OCR_DIR))

ocr_main = load_sidecar("ocr_service_main", "ocr/main.py")
app = ocr_main.app

from pipeline.extract_cells import default_template_cells, run_extract_cells  # noqa: E402

client = TestClient(app)


def test_field_keys_endpoint():
    resp = client.get("/v1/field-keys")
    assert resp.status_code == 200
    data = resp.json()
    assert data["keys"]
    assert data["default_cells"]


def test_run_extract_cells_manual_text(tmp_path):
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    path = tmp_path / "stamp.png"
    img.save(path)
    result = run_extract_cells(
        job_id=7,
        stamp_path=str(path),
        cells=[
            {
                "key": "approved_by",
                "bbox_norm": [0.1, 0.1, 0.5, 0.4],
                "category": "fio",
                "text": "Талдыкин",
            }
        ],
        pipeline_version="test",
    )
    assert result["fields"]["approved_by"]["value"] == "Талдыкин"
    assert result["fields"]["approved_by"]["conf"] == 1.0
    assert "annotated" in result["pipeline_version"]


def test_extract_cells_http(tmp_path, monkeypatch):
    monkeypatch.setattr(ocr_main, "UPLOADS_DIR", str(tmp_path))
    img = Image.new("RGB", (400, 200), color=(255, 255, 255))
    path = tmp_path / "stamp.png"
    img.save(path)
    resp = client.post(
        "/v1/extract-cells",
        json={
            "job_id": 9,
            "stamp_crop_path": str(path),
            "cells": default_template_cells()[:2],
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "designation" in data["fields"]
