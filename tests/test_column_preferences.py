"""Tests for column preferences across document tabs."""

from app.column_preferences import (
    DEFAULT_NOTIFICATION_COLUMNS,
    DEFAULT_ORDER_COLUMNS,
    get_visible_columns,
    merge_visible_columns,
    parse_profile_column_selection,
)


class _User:
    visible_columns = None


def test_legacy_list_visible_columns_maps_to_documents_tab():
    user = _User()
    user.visible_columns = ["designation", "project"]
    assert get_visible_columns(user, "documents") == ["designation", "project"]
    assert get_visible_columns(user, "notifications") == DEFAULT_NOTIFICATION_COLUMNS


def test_dict_visible_columns_per_tab():
    user = _User()
    user.visible_columns = {
        "documents": ["designation"],
        "notifications": ["number", "project"],
        "orders": ["name"],
    }
    assert get_visible_columns(user, "documents") == ["designation"]
    assert get_visible_columns(user, "notifications") == ["number", "project"]
    assert get_visible_columns(user, "orders") == ["name"]


def test_merge_profile_column_selection():
    class Form:
        def get(self, key):
            return "true" if key.endswith("_number") or key.endswith("_name") else None

    merged = merge_visible_columns(_User(), Form())
    assert "number" in merged["notifications"]
    assert "name" in merged["orders"]


def test_merge_visible_columns_returns_new_dict():
    user = _User()
    user.visible_columns = {"documents": ["designation"], "notifications": ["number"]}

    class Form:
        def get(self, key):
            return "true" if key == "col_documents_project" else None

    merged = merge_visible_columns(user, Form())
    assert merged is not user.visible_columns
    assert merged["documents"] == ["project"]
