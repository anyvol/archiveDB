from datetime import datetime

from app.models import BaseDocument, DocumentStatus, DocumentApplicability, Product, Project
from app.document_display import (
    format_document_products_cell,
    get_document_display_status,
    format_field_change,
)
from app.timezone_utils import format_date, format_datetime, date_input_value, parse_user_date, normalize_date_string


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


def test_format_datetime_includes_time_with_timezone():
    assert format_datetime(datetime(2026, 1, 1, 21, 30), "Europe/Moscow") == "02.01.2026 00:30"
    assert format_datetime(datetime(2026, 7, 7, 12, 0), "UTC") == "07.07.2026 12:00"


def test_date_input_value():
    assert date_input_value("2026-07-07") == "2026-07-07"
    assert date_input_value("07.07.2026") == "2026-07-07"
    assert date_input_value(None) == ""
    assert date_input_value("") == ""


def test_parse_user_date_accepts_russian_and_iso():
    assert parse_user_date("14.07.2026").date().isoformat() == "2026-07-14"
    assert parse_user_date("2026-07-14").date().isoformat() == "2026-07-14"
    assert parse_user_date("") is None
    assert parse_user_date(None) is None


def test_normalize_date_string():
    assert normalize_date_string("14.07.2026") == "2026-07-14"
    assert normalize_date_string("2026-07-14") == "2026-07-14"
    assert normalize_date_string("  ") is None


def test_format_document_products_cell_includes_own_and_applicability_products():
    project_a = Project(id=1, name="Alpha", slug="alpha")
    project_b = Project(id=2, name="Beta", slug="beta")
    own_product = Product(id=10, project_id=1, name="Own", slug="own", project=project_a)
    applied_product = Product(id=20, project_id=2, name="Applied", slug="applied", project=project_b)
    doc = _doc(product=own_product, product_id=10)
    doc.applicability_entries = [
        DocumentApplicability(
            id=1,
            document_id=doc.id,
            product_id=20,
            file_path="/tmp/a.pdf",
            file_name="a.pdf",
            created_by=1,
            product=applied_product,
        )
    ]

    assert format_document_products_cell(doc) == "Alpha / Own; Beta / Applied"


def test_format_document_products_cell_without_products():
    doc = _doc()
    doc.product = None
    doc.applicability_entries = []
    assert format_document_products_cell(doc) == "—"
