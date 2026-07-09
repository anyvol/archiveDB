"""Configurable role permission matrix stored in system settings."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserRole
from app.settings_store import SETTING_ROLE_PERMISSIONS, get_setting, set_setting

PERMISSION_DEFINITIONS: list[dict[str, str]] = [
    {"key": "view_documents", "label": "Просмотр и скачивание документов"},
    {"key": "create_document", "label": "Регистрация новых записей"},
    {"key": "upload_file", "label": "Загрузка и замена файлов"},
    {"key": "edit_document_metadata", "label": "Изменение метаданных (любые записи)"},
    {"key": "edit_own_document_metadata", "label": "Изменение метаданных своих записей"},
    {"key": "apply_formal_change", "label": "Внесение изменений в документ (ИИ)"},
    {"key": "request_minor_correction", "label": "Запрос на незначительное исправление"},
    {"key": "respond_correction_request", "label": "Ответ на запрос исправления"},
    {"key": "set_document_status", "label": "Утверждение / отправка на исправление"},
    {"key": "delete_document", "label": "Удаление записей"},
    {"key": "manage_projects", "label": "Управление проектами"},
    {"key": "add_document_links", "label": "Добавление ссылок между записями"},
    {"key": "remove_document_links", "label": "Удаление ссылок"},
    {"key": "add_applicability", "label": "Добавление применяемости"},
    {"key": "remove_applicability", "label": "Удаление применяемости"},
]

CONFIGURABLE_ROLES = (
    UserRole.user,
    UserRole.reviewer,
    UserRole.admin,
)

DEFAULT_ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    UserRole.user.value: {
        "view_documents": True,
        "create_document": True,
        "upload_file": True,
        "edit_document_metadata": False,
        "edit_own_document_metadata": True,
        "apply_formal_change": True,
        "request_minor_correction": True,
        "respond_correction_request": False,
        "set_document_status": False,
        "delete_document": False,
        "manage_projects": False,
        "add_document_links": True,
        "remove_document_links": False,
        "add_applicability": True,
        "remove_applicability": False,
    },
    UserRole.reviewer.value: {
        "view_documents": True,
        "create_document": False,
        "upload_file": False,
        "edit_document_metadata": False,
        "edit_own_document_metadata": False,
        "apply_formal_change": False,
        "request_minor_correction": False,
        "respond_correction_request": True,
        "set_document_status": True,
        "delete_document": False,
        "manage_projects": False,
        "add_document_links": True,
        "remove_document_links": False,
        "add_applicability": True,
        "remove_applicability": False,
    },
    UserRole.admin.value: {
        "view_documents": True,
        "create_document": True,
        "upload_file": True,
        "edit_document_metadata": True,
        "edit_own_document_metadata": True,
        "apply_formal_change": True,
        "request_minor_correction": True,
        "respond_correction_request": True,
        "set_document_status": True,
        "delete_document": True,
        "manage_projects": True,
        "add_document_links": True,
        "remove_document_links": True,
        "add_applicability": True,
        "remove_applicability": True,
    },
}

_role_permissions_cache: dict[str, dict[str, bool]] = deepcopy(DEFAULT_ROLE_PERMISSIONS)


def _normalize_matrix(raw: Any) -> dict[str, dict[str, bool]]:
    matrix = deepcopy(DEFAULT_ROLE_PERMISSIONS)
    if not isinstance(raw, dict):
        return matrix

    for role in CONFIGURABLE_ROLES:
        role_key = role.value
        role_data = raw.get(role_key)
        if not isinstance(role_data, dict):
            continue
        for perm in PERMISSION_DEFINITIONS:
            key = perm["key"]
            if key in role_data:
                matrix[role_key][key] = bool(role_data[key])
    return matrix


def get_cached_role_permissions() -> dict[str, dict[str, bool]]:
    return _role_permissions_cache


def set_cached_role_permissions(matrix: dict[str, dict[str, bool]]) -> None:
    global _role_permissions_cache
    _role_permissions_cache = _normalize_matrix(matrix)


async def load_role_permissions(session: AsyncSession) -> dict[str, dict[str, bool]]:
    raw = await get_setting(session, SETTING_ROLE_PERMISSIONS, None)
    matrix = _normalize_matrix(raw)
    set_cached_role_permissions(matrix)
    return matrix


async def save_role_permissions(
    session: AsyncSession,
    matrix: dict[str, dict[str, bool]],
    *,
    updated_by_id: int | None = None,
) -> dict[str, dict[str, bool]]:
    normalized = _normalize_matrix(matrix)
    await set_setting(session, SETTING_ROLE_PERMISSIONS, normalized, updated_by_id=updated_by_id)
    set_cached_role_permissions(normalized)
    return normalized


def role_has_permission(role: UserRole, permission_key: str) -> bool:
    if role == UserRole.master_admin:
        return True
    role_key = role.value
    role_matrix = get_cached_role_permissions().get(role_key, {})
    default = DEFAULT_ROLE_PERMISSIONS.get(role_key, {}).get(permission_key, False)
    return bool(role_matrix.get(permission_key, default))
