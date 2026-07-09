from app.models import UserRole
from app.role_permissions import (
    DEFAULT_ROLE_PERMISSIONS,
    role_has_permission,
    set_cached_role_permissions,
)


def setup_function():
    set_cached_role_permissions(DEFAULT_ROLE_PERMISSIONS)


def test_master_admin_always_has_permission():
    assert role_has_permission(UserRole.master_admin, "delete_document")


def test_reviewer_default_cannot_delete():
    assert not role_has_permission(UserRole.reviewer, "delete_document")
    assert role_has_permission(UserRole.reviewer, "set_document_status")


def test_custom_matrix_overrides_default():
    matrix = {
        role.value: dict(DEFAULT_ROLE_PERMISSIONS[role.value])
        for role in (UserRole.user, UserRole.reviewer, UserRole.admin)
    }
    matrix[UserRole.reviewer.value]["delete_document"] = True
    set_cached_role_permissions(matrix)
    assert role_has_permission(UserRole.reviewer, "delete_document")
