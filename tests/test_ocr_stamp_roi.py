"""Tests for format-bound stamp ROI helpers."""

from app.ocr.annotate import DEFAULT_STAMP_ROI_BY_FORMAT, default_stamp_roi_for_format, normalize_stamp_roi


def test_a4_stamp_roi_differs_from_a3():
    a4 = default_stamp_roi_for_format("A4")
    a3 = default_stamp_roi_for_format("A3")
    assert a4 != a3
    assert a4 == DEFAULT_STAMP_ROI_BY_FORMAT["A4"]


def test_normalize_stamp_roi():
    assert normalize_stamp_roi([0.1, 0.2, 0.9, 0.95]) == [0.1, 0.2, 0.9, 0.95]
    assert normalize_stamp_roi([0.9, 0.2, 0.1, 0.95]) is None  # inverted
    assert normalize_stamp_roi(None) is None
