"""Auth routes for Codex OAuth and API key management."""

import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from loguru import logger
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import AsyncSessionLocal, get_db
from app.models import AuthToken
from app.services.ai_service import ai_service
from app.services.bybit_service import bybit_service

router = APIRouter()
_oauth_state: dict[str, str] = {}


class APIKeysUpdate(BaseModel):
    bybit_api_key: str = ""
    bybit_api_secret: str = ""
    deepseek_api_key: Optional[str] = None


class AuthStatus(BaseModel):
    codex_connected: bool
    deepseek_configured: bool
    bybit_configured: bool
    codex_expires_at: Optional[str] = None


def _write_env_updates(path_str: str, updates: dict[str, str]) -> None:
    path = Path(path_str)
    content = path.read_text(encoding="utf-8") if path.exists() else ""
    lines = content.splitlines()

    for key, value in updates.items():
        replacement = f"{key}={value}"
        for index, line in enumerate(lines):
            if line.startswith(f"{key}="):
                lines[index] = replacement
                break
        else:
            lines.append(replacement)

    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


@router.get("/status", response_model=AuthStatus)
async def auth_status(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    codex = result.scalar_one_or_none()
    codex_ok = codex and codex.access_token and (
        not codex.expires_at or codex.expires_at > datetime.now(timezone.utc)
    )

    result = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
    deepseek = result.scalar_one_or_none()

    return AuthStatus(
        codex_connected=bool(codex_ok),
        deepseek_configured=bool((deepseek and deepseek.access_token) or settings.DEEPSEEK_API_KEY),
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
async def save_api_keys(payload: APIKeysUpdate, db: AsyncSession = Depends(get_db)):
    if payload.deepseek_api_key:
        result = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
        existing = result.scalar_one_or_none()
        if existing:
            existing.access_token = payload.deepseek_api_key
        else:
            db.add(AuthToken(provider="deepseek", access_token=payload.deepseek_api_key))
        ai_service.api_key = payload.deepseek_api_key
        await db.commit()

    if payload.bybit_api_key and payload.bybit_api_secret:
        try:
            _write_env_updates(
                settings.ENV_FILE_PATH,
                {
                    "BYBIT_API_KEY": payload.bybit_api_key,
                    "BYBIT_API_SECRET": payload.bybit_api_secret,
                },
            )
            settings.BYBIT_API_KEY = payload.bybit_api_key
            settings.BYBIT_API_SECRET = payload.bybit_api_secret
            bybit_service.reload_credentials(payload.bybit_api_key, payload.bybit_api_secret)
        except Exception as exc:
            logger.warning(f"Could not update env file: {exc}")

    return {
        "success": True,
        "message": "Saved. Bybit changes are active now and persist after restart.",
    }


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

    result = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
    deepseek = result.scalar_one_or_none()
    if deepseek and deepseek.access_token:
        ai_service.api_key = deepseek.access_token
