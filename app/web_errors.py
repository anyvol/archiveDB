"""Browser-friendly error responses for HTML form submissions."""

from __future__ import annotations

from urllib.parse import quote

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import ROOT_PATH, url_path

_FORM_POST_PREFIXES = (
    "/register",
    "/profile",
    "/documents/create",
    "/documents/",
    "/login",
)

_API_PREFIXES = ("/users", "/docs", "/api/")


def _route_path(request: Request) -> str:
    path = request.scope.get("path", request.url.path)
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def is_browser_form_post(request: Request) -> bool:
    if request.method != "POST":
        return False

    path = _route_path(request)
    if any(path.startswith(prefix) for prefix in _API_PREFIXES):
        return False
    if not any(path == prefix or path.startswith(prefix) for prefix in _FORM_POST_PREFIXES):
        return False

    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
        return True

    accept = request.headers.get("accept", "")
    return "text/html" in accept


def validation_message(errors: list[dict]) -> str:
    messages: list[str] = []
    for error in errors:
        loc = error.get("loc", ())
        field = loc[-1] if loc else "поле"
        if isinstance(field, int):
            field = "данные"
        err_type = error.get("type", "")
        if err_type == "missing":
            messages.append(f"Не заполнено обязательное поле «{field}».")
        elif err_type == "string_too_short":
            messages.append(f"Поле «{field}» слишком короткое.")
        elif err_type == "string_too_long":
            messages.append(f"Поле «{field}» слишком длинное.")
        elif err_type == "value_error":
            messages.append(str(error.get("msg", "Некорректное значение.")))
        else:
            msg = error.get("msg", "Некорректные данные формы.")
            messages.append(str(msg))
    return " ".join(messages) if messages else "Некорректные данные формы."


def http_error_message(detail) -> str:
    if isinstance(detail, str):
        return detail
    if isinstance(detail, list):
        return validation_message(detail)
    return "Произошла ошибка при обработке запроса."


def browser_error_redirect(request: Request, message: str, status_code: int = 400) -> RedirectResponse | HTMLResponse:
    path = _route_path(request)
    encoded = quote(message, safe="")

    if path == "/register" or path.endswith("/register"):
        return RedirectResponse(
            url=url_path(f"/register?error=message&msg={encoded}"),
            status_code=303,
        )

    if path == "/profile" or path.endswith("/profile"):
        return RedirectResponse(
            url=url_path(f"/profile?error=message&msg={encoded}"),
            status_code=303,
        )

    if path == "/documents/create" or path.endswith("/documents/create"):
        return RedirectResponse(
            url=url_path(f"/documents?create_error={encoded}"),
            status_code=303,
        )

    if "/documents/" in path and path.endswith("/edit"):
        doc_id = path.rstrip("/").split("/")[-2]
        return RedirectResponse(
            url=url_path(f"/documents/{doc_id}/edit?error={encoded}"),
            status_code=303,
        )

    if "/documents/" in path and path.endswith("/upload"):
        doc_id = path.rstrip("/").split("/")[-2]
        return RedirectResponse(
            url=url_path(f"/documents/{doc_id}/upload?error=server&msg={encoded}"),
            status_code=303,
        )

    if "/documents/" in path and (path.endswith("/status") or path.endswith("/delete")):
        return RedirectResponse(
            url=url_path(f"/documents?action_error={encoded}"),
            status_code=303,
        )

    if path == "/login" or path.endswith("/login"):
        return RedirectResponse(url=url_path("/login?error=true"), status_code=303)

    return HTMLResponse(
        content=f"<html><body><p>{message}</p><p><a href=\"{url_path('/documents')}\">Назад</a></p></body></html>",
        status_code=status_code,
    )


async def handle_validation_error(request: Request, exc: RequestValidationError):
    if is_browser_form_post(request):
        message = validation_message(exc.errors())
        return browser_error_redirect(request, message, status_code=422)
    return JSONResponse(status_code=422, content={"detail": exc.errors()})


async def handle_http_exception(request: Request, exc: StarletteHTTPException):
    if is_browser_form_post(request):
        message = http_error_message(exc.detail)
        return browser_error_redirect(request, message, status_code=exc.status_code)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
