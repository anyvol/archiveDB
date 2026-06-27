from app.models import BaseDocument, DocumentStatus
from app.document_display import get_document_display_status, format_field_change


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
    label, css = get_document_display_status(_doc(file_name="a.pdf", status=DocumentStatus.verified))
    assert label == "Проверено"
    assert css == "status-verified"


def test_format_field_change():
    assert format_field_change("наименование", "A", "B") == "наименование: «A» → «B»"
    assert format_field_change("наименование", "A", "A") is None
