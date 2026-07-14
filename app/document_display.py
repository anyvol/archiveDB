"""Display helpers for documents in UI."""

from app.models import BaseDocument, DOCUMENT_STATUS_LABELS, DISPLAY_STATUS_NO_FILE, DocumentStatus, Product

STATUS_CSS_CLASS = {
    DocumentStatus.pending_review: "status-pending",
    DocumentStatus.approved: "status-approved",
    DocumentStatus.requires_correction: "status-correction",
    DocumentStatus.correction_requested: "status-correction-requested",
    DocumentStatus.auto_draft: "status-auto-draft",
}


def get_document_related_products(doc: BaseDocument) -> list[Product]:
    """Return the document's own product plus applicability products, without duplicates."""
    seen: set[int] = set()
    related: list[Product] = []
    if doc.product and doc.product.id not in seen:
        seen.add(doc.product.id)
        related.append(doc.product)
    for entry in doc.applicability_entries or []:
        product = entry.product
        if product and product.id not in seen:
            seen.add(product.id)
            related.append(product)
    return related


def format_document_products_cell(doc: BaseDocument) -> str:
    products = get_document_related_products(doc)
    if not products:
        return "—"
    return "; ".join(
        f"{product.project.name} / {product.name}" if product.project else product.name
        for product in products
    )


def get_document_primary_product_name(doc: BaseDocument) -> str:
    products = get_document_related_products(doc)
    if not products:
        return ""
    return products[0].name


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
