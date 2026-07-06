"""Tests for sliding session helpers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException, Request

from app.auth import SESSION_EXPIRED_DETAIL, SESSION_EXPIRED_MESSAGE
from app.session_helpers import (
    resolve_authenticated_user,
    session_expired_response,
    wants_json_response,
)


def _request(accept: str = "text/html") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/documents",
        "headers": [(b"accept", accept.encode())],
    }
    return Request(scope)


def test_wants_json_response_from_accept_header():
    assert wants_json_response(_request("application/json")) is True
    assert wants_json_response(_request("text/html, application/json")) is True
    assert wants_json_response(_request("text/html")) is False


def test_session_expired_response_html_redirect():
    response = session_expired_response(_request("text/html"))
    assert response.status_code == 303
    assert "expired=1" in response.headers["location"]


def test_session_expired_response_json():
    response = session_expired_response(_request("application/json"))
    assert response.status_code == 401
    assert response.body
    payload = response.body.decode()
    assert SESSION_EXPIRED_DETAIL in payload
    assert SESSION_EXPIRED_MESSAGE in payload


@pytest.mark.asyncio
async def test_resolve_authenticated_user_without_cookie():
    session = AsyncMock()
    result = await resolve_authenticated_user(_request("application/json"), None, session)
    assert result.status_code == 401


@pytest.mark.asyncio
async def test_resolve_authenticated_user_with_valid_cookie():
    session = AsyncMock()
    user = MagicMock()
    with patch("app.session_helpers.get_current_user_from_token", AsyncMock(return_value=user)):
        result = await resolve_authenticated_user(_request(), "Bearer token", session)
    assert result is user


@pytest.mark.asyncio
async def test_resolve_authenticated_user_with_invalid_cookie():
    session = AsyncMock()
    with patch(
        "app.session_helpers.get_current_user_from_token",
        AsyncMock(side_effect=HTTPException(status_code=401, detail="bad")),
    ):
        result = await resolve_authenticated_user(_request("application/json"), "Bearer bad", session)
    assert result.status_code == 401


def test_get_login_from_valid_token_roundtrip():
    from app.auth import create_access_token, get_login_from_valid_token

    token = create_access_token({"sub": "alice"})
    assert get_login_from_valid_token(f"Bearer {token}") == "alice"
    assert get_login_from_valid_token("Bearer invalid") is None
