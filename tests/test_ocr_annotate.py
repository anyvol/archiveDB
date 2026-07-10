"""Tests for OCR annotation helpers (phase 2)."""

from app.ocr.annotate import (
    DEFAULT_CELL_TEMPLATE,
    cells_from_extraction,
    normalize_labels_payload,
)
from fastapi import HTTPException
import pytest


def test_default_template_has_core_fields():
    keys = {c["key"] for c in DEFAULT_CELL_TEMPLATE}
    assert "designation" in keys
    assert "approved_by" in keys
    assert "doc_name" in keys


def test_cells_from_extraction_uses_bbox_norm():
    class E:
        fields = {
            "designation": {
                "value": "АБВГ.123456.001",
                "bbox_norm": [0.1, 0.1, 0.5, 0.2],
                "bbox": [10, 10, 50, 20],
            }
        }
        geometry = {"stamp_size": [100, 100]}

    cells = cells_from_extraction(E())
    des = next(c for c in cells if c["key"] == "designation")
    assert des["bbox_norm"] == [0.1, 0.1, 0.5, 0.2]


def test_normalize_labels_requires_cells():
    with pytest.raises(HTTPException):
        normalize_labels_payload({"cells": []})


def test_normalize_labels_ok():
    labels = normalize_labels_payload(
        {
            "cells": [
                {"key": "developed_by", "bbox_norm": [0.1, 0.2, 0.3, 0.4], "text": "Талдыкин"},
            ],
            "stamp_size": [800, 400],
        }
    )
    assert labels["cells"][0]["text"] == "Талдыкин"
    assert labels["stamp_size"] == [800, 400]
