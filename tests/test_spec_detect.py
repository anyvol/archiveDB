"""Tests for multi-page specification detection in OCR pipeline."""

import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np

OCR_DIR = Path(__file__).resolve().parents[1] / "ocr"
sys.path.insert(0, str(OCR_DIR))

from pipeline.spec_detect import detect_specification_pages  # noqa: E402


def _blank_page() -> np.ndarray:
    return np.zeros((800, 1200, 3), dtype=np.uint8)


def test_detect_specification_pages_single_page():
    result = detect_specification_pages([_blank_page()])
    assert result["has_specification"] is False
    assert result["spec_page_indices"] == []
    assert result["designations"] == []


def test_detect_specification_pages_finds_title_page():
    pages = [_blank_page(), _blank_page()]

    def fake_ocr(image, category=None):
        h = image.shape[0]
        if h < 200:
            return {"raw": "СПЕЦИФИКАЦИЯ", "value": "СПЕЦИФИКАЦИЯ", "conf": 0.9}
        return {
            "raw": "ФЕТР.123456.001СБ ФЕТР.123456.002 ГЧ ФЕТР.123456.003ГЧ",
            "value": "ФЕТР.123456.001СБ ФЕТР.123456.002 ГЧ ФЕТР.123456.003ГЧ",
            "conf": 0.8,
        }

    with patch("pipeline.spec_detect.ocr_cell", side_effect=fake_ocr):
        result = detect_specification_pages(pages)

    assert result["has_specification"] is True
    assert 1 in result["spec_page_indices"]
    assert "ФЕТР.123456.001СБ" in result["designations"]
