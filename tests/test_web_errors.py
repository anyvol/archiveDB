"""Tests for browser-friendly web error handling."""

from app.web_errors import (
    browser_error_redirect,
    http_error_message,
    is_browser_form_post,
    validation_message,
)


class _FakeRequest:
    def __init__(self, method: str, path: str, headers: dict | None = None):
        self.method = method
        self.scope = {"path": path, "root_path": ""}
        self.url = type("URL", (), {"path": path})()
        self.headers = headers or {}


def test_is_browser_form_post_for_register():
    request = _FakeRequest(
        "POST",
        "/register",
        {"content-type": "application/x-www-form-urlencoded"},
    )
    assert is_browser_form_post(request) is True


def test_is_browser_form_post_false_for_api():
    request = _FakeRequest(
        "POST",
        "/users/register",
        {"content-type": "application/json"},
    )
    assert is_browser_form_post(request) is False


def test_validation_message_missing_field():
    message = validation_message(
        [{"type": "missing", "loc": ("body", "login"), "msg": "Field required"}]
    )
    assert "login" in message


def test_http_error_message_string_detail():
    assert http_error_message("Пароли не совпадают") == "Пароли не совпадают"


def test_browser_error_redirect_register():
    request = _FakeRequest(
        "POST",
        "/register",
        {"content-type": "application/x-www-form-urlencoded"},
    )
    response = browser_error_redirect(request, "Пароли не совпадают")
    assert response.status_code == 303
    assert "error=message" in response.headers["location"]
    assert "msg=" in response.headers["location"]
