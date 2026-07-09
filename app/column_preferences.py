"""Document table column visibility preferences."""

DOCUMENT_COLUMNS = [
    ("designation", "Обозначение"),
    ("org_name", "Компания"),
    ("project", "Проект"),
    ("product", "Изделие"),
    ("okpo", "ОКПО"),
    ("developed_by", "Разработал"),
    ("doc_name", "Наименование"),
    ("file_name", "Файл"),
    ("type", "Тип"),
    ("created_by", "Зарегистрировал"),
    ("created_at", "Дата рег."),
    ("last_update", "Обновлено"),
    ("status", "Статус"),
]

NOTIFICATION_COLUMNS = [
    ("number", "Номер извещения"),
    ("change_number", "Номер изменения"),
    ("change_date", "Дата изменения"),
    ("created_at", "Дата регистрации"),
    ("project", "Проект"),
    ("product", "Изделие"),
]

ORDER_COLUMNS = [
    ("number", "Номер"),
    ("name", "Название"),
    ("order_date", "Дата"),
]

TAB_COLUMN_DEFINITIONS = {
    "documents": DOCUMENT_COLUMNS,
    "notifications": NOTIFICATION_COLUMNS,
    "orders": ORDER_COLUMNS,
}

DEFAULT_VISIBLE_COLUMNS = [key for key, _ in DOCUMENT_COLUMNS]
DEFAULT_NOTIFICATION_COLUMNS = [key for key, _ in NOTIFICATION_COLUMNS]
DEFAULT_ORDER_COLUMNS = [key for key, _ in ORDER_COLUMNS]

DEFAULT_TAB_COLUMNS = {
    "documents": DEFAULT_VISIBLE_COLUMNS,
    "notifications": DEFAULT_NOTIFICATION_COLUMNS,
    "orders": DEFAULT_ORDER_COLUMNS,
}


def _normalize_stored_columns(stored) -> dict[str, list[str]]:
    if isinstance(stored, dict):
        return stored
    if isinstance(stored, list):
        return {"documents": stored}
    return {}


def get_visible_columns(user, tab: str = "documents") -> list[str]:
    definitions = TAB_COLUMN_DEFINITIONS.get(tab, DOCUMENT_COLUMNS)
    valid = {key for key, _ in definitions}
    default = [key for key, _ in definitions]
    stored = _normalize_stored_columns(getattr(user, "visible_columns", None))
    raw = stored.get(tab)
    if not raw:
        return list(default)
    filtered = [key for key in raw if key in valid]
    return filtered or list(default)


def parse_profile_column_selection(form_data, tab: str) -> list[str]:
    definitions = TAB_COLUMN_DEFINITIONS.get(tab, DOCUMENT_COLUMNS)
    selected = [key for key, _ in definitions if form_data.get(f"col_{tab}_{key}") == "true"]
    if not selected:
        return list(DEFAULT_TAB_COLUMNS.get(tab, DEFAULT_VISIBLE_COLUMNS))
    return selected


def merge_visible_columns(user, form_data) -> dict[str, list[str]]:
    # Always return a new dict so SQLAlchemy detects JSON column changes.
    return {
        tab: parse_profile_column_selection(form_data, tab)
        for tab in TAB_COLUMN_DEFINITIONS
    }
