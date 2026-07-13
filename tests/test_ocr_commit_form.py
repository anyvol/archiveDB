"""Tests for OCR commit form parsing helpers."""

from app.ocr.commit import _form_int_list


def test_form_int_list_parses_single_and_multiple_values():
    assert _form_int_list({"additional_product_ids": "12"}, "additional_product_ids") == [12]
    assert _form_int_list(
        {"additional_product_ids": ["12", "34", ""]},
        "additional_product_ids",
    ) == [12, 34]
    assert _form_int_list({}, "additional_product_ids") == []
