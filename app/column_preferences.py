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

DEFAULT_VISIBLE_COLUMNS = [key for key, _ in DOCUMENT_COLUMNS]


def get_visible_columns(user) -> list[str]:
    stored = getattr(user, "visible_columns", None)
    if not stored:
        return list(DEFAULT_VISIBLE_COLUMNS)
    valid = {key for key, _ in DOCUMENT_COLUMNS}
    filtered = [key for key in stored if key in valid]
    return filtered or list(DEFAULT_VISIBLE_COLUMNS)
