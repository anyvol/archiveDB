"""Tests for departments and user role labels."""

from app.models import DEPARTMENTS, USER_ROLE_LABELS, UserRole


def test_departments_include_integration_and_service():
    assert "Отдел интеграции и сопровождения" in DEPARTMENTS
    assert "Сервисный отдел" in DEPARTMENTS


def test_user_role_labels_cover_all_roles():
    assert USER_ROLE_LABELS[UserRole.admin] == "Администратор"
    assert USER_ROLE_LABELS[UserRole.user] == "Обычный пользователь"
    assert USER_ROLE_LABELS[UserRole.reviewer] == "Ревьюер"
    assert set(USER_ROLE_LABELS) == set(UserRole)
