"""Browser session helpers: expired-session responses and auth resolution."""

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse, RedirectResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import (
    SESSION_EXPIRED_DETAIL,
    SESSION_EXPIRED_MESSAGE,
    get_current_user_from_token,
)
from app.config import url_path
from app.models import User


def wants_json_response(request: Request) -> bool:
    accept = (request.headers.get("accept") or "").lower()
    if "application/json" in accept:
        return True
    if request.headers.get("x-requested-with", "").lower() == "xmlhttprequest":
        return True
    return False


def session_expired_response(request: Request | None = None, *, force_json: bool = False) -> Response:
    if force_json or (request is not None and wants_json_response(request)):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": SESSION_EXPIRED_DETAIL, "message": SESSION_EXPIRED_MESSAGE},
        )
    return RedirectResponse(url=url_path("/login?expired=1"), status_code=status.HTTP_303_SEE_OTHER)


async def resolve_authenticated_user(
    request: Request,
    access_token: str | None,
    session: AsyncSession,
    *,
    force_json: bool = False,
) -> User | Response:
    if not access_token:
        return session_expired_response(request, force_json=force_json)
    try:
        return await get_current_user_from_token(access_token=access_token, db=session)
    except HTTPException:
        return session_expired_response(request, force_json=force_json)
