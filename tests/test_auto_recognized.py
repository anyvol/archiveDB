"""Tests for auto_recognized flag on OCR commit."""

from app.ocr.commit import _form_int_list


def test_commit_sets_auto_recognized_in_model_field_name():
    # Guard against accidental rename — commit must set BaseDocument.auto_recognized.
    from app.models import BaseDocument

    assert "auto_recognized" in BaseDocument.__table__.columns
