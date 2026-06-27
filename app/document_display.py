"""Display helpers for documents in UI."""

from app.models import BaseDocument, DOCUMENT_STATUS_LABELS, DISPLAY_STATUS_NO_FILE, DocumentStatus

STATUS_CSS_CLASS = {
    DocumentStatus.pending_review: "status-pending",
    DocumentStatus.verified: "status-verified",
    DocumentStatus.requires_correction: "status-correction",
}


def get_document_display_status(doc: BaseDocument) -> tuple[str, str]:
    """Return (label, css_class) for status column."""
    if not doc.file_name:
        return DISPLAY_STATUS_NO_FILE, "status-no-file"
    return DOCUMENT_STATUS_LABELS[doc.status], STATUS_CSS_CLASS[doc.status]


def format_field_change(label: str, old_value: str | None, new_value: str | None) -> str | None:
    old_display = old_value or "—"
    new_display = new_value or "—"
    if old_display == new_display:
        return None
    return f"{label}: «{old_display}» → «{new_display}»"
