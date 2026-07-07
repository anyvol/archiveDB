from datetime import datetime

from app.models import BaseDocument, DocumentStatus
from app.document_display import get_document_display_status, format_field_change
from app.timezone_utils import format_date


def _doc(**kwargs) -> BaseDocument:
    defaults = {
        "id": 1,
        "type": "DD",
        "created_by": "User",
        "uploaded_by": 1,
        "status": DocumentStatus.pending_review,
        "file_name": None,
    }
    defaults.update(kwargs)
    return BaseDocument(**defaults)


def test_display_status_no_file():
    label, css = get_document_display_status(_doc(file_name=None))
    assert label == "Файл не загружен"
    assert css == "status-no-file"


def test_display_status_with_file():
    label, css = get_document_display_status(_doc(file_name="a.pdf", status=DocumentStatus.approved))
    assert label == "Утверждено"
    assert css == "status-approved"


def test_display_status_pending_and_correction():
    _, pending_css = get_document_display_status(_doc(file_name="a.pdf", status=DocumentStatus.pending_review))
    _, correction_css = get_document_display_status(_doc(file_name="a.pdf", status=DocumentStatus.requires_correction))
    assert pending_css == "status-pending"
    assert correction_css == "status-correction"


def test_format_field_change():
    assert format_field_change("наименование", "A", "B") == "наименование: «A» → «B»"
    assert format_field_change("наименование", "A", "A") is None


def test_format_date_uses_configured_timezone_and_day_month_year():
    assert format_date(datetime(2026, 1, 1, 21, 30), "Europe/Moscow") == "02.01.2026"
    assert format_date("2026-07-07") == "07.07.2026"
