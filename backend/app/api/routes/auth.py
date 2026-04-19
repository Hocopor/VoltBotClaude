"""Auth routes for app login and Codex OAuth."""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import AuthToken
from app.services.ai_service import ai_service
from app.security import (
    create_session_token,
    get_authenticated_login_from_request,
    require_authenticated_user,
    session_cookie_settings,
    verify_password,
)

router = APIRouter()
_oauth_state: dict[str, str] = {}


class AuthStatus(BaseModel):
    authenticated: bool
    app_login_configured: bool
    app_login: Optional[str] = None
    codex_connected: bool
    deepseek_configured: bool
    bybit_configured: bool
    codex_expires_at: Optional[str] = None


class LoginRequest(BaseModel):
    login: str
    password: str


@router.get("/session")
async def auth_session(request: Request):
    current_login = get_authenticated_login_from_request(request)
    return {"authenticated": bool(current_login), "login": current_login}


@router.post("/login")
async def app_login(payload: LoginRequest, response: Response):
    if not settings.APP_AUTH_PASSWORD_HASH:
        raise HTTPException(500, "Application login is not configured")
    if payload.login != settings.APP_AUTH_LOGIN:
        raise HTTPException(401, "Invalid login or password")
    if not verify_password(payload.password, settings.APP_AUTH_PASSWORD_HASH):
        raise HTTPException(401, "Invalid login or password")

    response.set_cookie(
        value=create_session_token(payload.login),
        **session_cookie_settings(),
    )
    return {"success": True, "login": payload.login}


@router.post("/logout")
async def app_logout(response: Response):
    response.delete_cookie(session_cookie_settings()["key"], path="/")
    return {"success": True}


@router.get("/status", response_model=AuthStatus)
async def auth_status(
    db: AsyncSession = Depends(get_db),
    current_login: Optional[str] = Depends(require_authenticated_user),
):
    result = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    codex = result.scalar_one_or_none()
    codex_ok = codex and codex.access_token and (
        not codex.expires_at or codex.expires_at > datetime.now(timezone.utc)
    )

    return AuthStatus(
        authenticated=bool(current_login),
        app_login_configured=bool(settings.APP_AUTH_PASSWORD_HASH),
        app_login=settings.APP_AUTH_LOGIN if settings.APP_AUTH_PASSWORD_HASH else None,
        codex_connected=bool(codex_ok),
        deepseek_configured=bool(settings.DEEPSEEK_API_KEY),
        bybit_configured=bool(settings.BYBIT_API_KEY and settings.BYBIT_API_SECRET),
        codex_expires_at=codex.expires_at.isoformat() if codex and codex.expires_at else None,
    )


@router.get("/codex/login")
async def codex_login():
    if not settings.OPENAI_CLIENT_ID:
        raise HTTPException(400, "Codex OAuth not configured")

    state = secrets.token_urlsafe(32)
    _oauth_state[state] = datetime.now(timezone.utc).isoformat()
    return {
        "auth_url": (
            f"https://auth.openai.com/authorize?client_id={settings.OPENAI_CLIENT_ID}"
            f"&redirect_uri={settings.OPENAI_REDIRECT_URI}&response_type=code"
            f"&scope=openid+email&state={state}"
        ),
        "state": state,
    }


@router.get("/codex/callback")
async def codex_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    if state not in _oauth_state:
        raise HTTPException(400, "Invalid OAuth state")

    del _oauth_state[state]

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://auth.openai.com/oauth/token",
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.OPENAI_CLIENT_ID,
                    "client_secret": settings.OPENAI_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.OPENAI_REDIRECT_URI,
                },
            )
            response.raise_for_status()
            token_data = response.json()
    except Exception as exc:
        raise HTTPException(400, f"OAuth failed: {exc}") from exc

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_data.get("expires_in", 3600))
    result = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    existing = result.scalar_one_or_none()

    if existing:
        existing.access_token = token_data.get("access_token")
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = expires_at
        existing.extra_data = token_data
    else:
        db.add(
            AuthToken(
                provider="codex",
                access_token=token_data.get("access_token"),
                refresh_token=token_data.get("refresh_token"),
                expires_at=expires_at,
                extra_data=token_data,
            )
        )

    await db.commit()
    ai_service.set_codex_token(token_data.get("access_token", ""))
    return RedirectResponse(url="/?auth=codex_success")


@router.delete("/codex/disconnect")
async def codex_disconnect(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    token = result.scalar_one_or_none()
    if token:
        await db.delete(token)
        await db.commit()

    ai_service.set_codex_token("")
    return {"success": True}


@router.post("/apikeys")
async def save_api_keys(
    current_login: Optional[str] = Depends(require_authenticated_user),
):
    raise HTTPException(
        status_code=400,
        detail="Bybit and DeepSeek API keys are managed via .env on the server, not via the web UI.",
    )


@router.post("/load-tokens")
async def load_tokens_endpoint(db: AsyncSession = Depends(get_db)):
    await _load_tokens_from_db(db)
    return {"loaded": True}


async def load_saved_tokens_internal():
    async with AsyncSessionLocal() as db:
        await _load_tokens_from_db(db)


async def _load_tokens_from_db(db: AsyncSession):
    result = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    codex = result.scalar_one_or_none()
    if codex and codex.access_token and (
        not codex.expires_at or codex.expires_at > datetime.now(timezone.utc)
    ):
        ai_service.set_codex_token(codex.access_token)

    ai_service.api_key = settings.DEEPSEEK_API_KEY
