"""Auth Routes — Codex OAuth + API key management"""
import secrets
from datetime import datetime, timezone, timedelta
from typing import Optional
from loguru import logger
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import httpx
from app.database import get_db, AsyncSessionLocal
from app.models import AuthToken
from app.config import settings
from app.services.ai_service import ai_service

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

@router.get("/status", response_model=AuthStatus)
async def auth_status(db: AsyncSession = Depends(get_db)):
    r1 = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    codex = r1.scalar_one_or_none()
    codex_ok = codex and codex.access_token and (not codex.expires_at or codex.expires_at > datetime.now(timezone.utc))
    r2 = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
    ds = r2.scalar_one_or_none()
    return AuthStatus(
        codex_connected=bool(codex_ok),
        deepseek_configured=bool((ds and ds.access_token) or settings.DEEPSEEK_API_KEY),
        bybit_configured=bool(settings.BYBIT_API_KEY and settings.BYBIT_API_SECRET),
        codex_expires_at=codex.expires_at.isoformat() if codex and codex.expires_at else None,
    )

@router.get("/codex/login")
async def codex_login():
    if not settings.OPENAI_CLIENT_ID:
        raise HTTPException(400, "Codex OAuth not configured")
    state = secrets.token_urlsafe(32)
    _oauth_state[state] = datetime.now(timezone.utc).isoformat()
    return {"auth_url": (
        f"https://auth.openai.com/authorize?client_id={settings.OPENAI_CLIENT_ID}"
        f"&redirect_uri={settings.OPENAI_REDIRECT_URI}&response_type=code&scope=openid+email&state={state}"
    ), "state": state}

@router.get("/codex/callback")
async def codex_callback(code: str, state: str, db: AsyncSession = Depends(get_db)):
    if state not in _oauth_state:
        raise HTTPException(400, "Invalid OAuth state")
    del _oauth_state[state]
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post("https://auth.openai.com/oauth/token", json={
                "grant_type": "authorization_code", "client_id": settings.OPENAI_CLIENT_ID,
                "client_secret": settings.OPENAI_CLIENT_SECRET, "code": code,
                "redirect_uri": settings.OPENAI_REDIRECT_URI,
            })
            resp.raise_for_status()
            td = resp.json()
    except Exception as e:
        raise HTTPException(400, f"OAuth failed: {e}")
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=td.get("expires_in", 3600))
    r = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    ex = r.scalar_one_or_none()
    if ex:
        ex.access_token = td.get("access_token"); ex.refresh_token = td.get("refresh_token")
        ex.expires_at = expires_at; ex.extra_data = td
    else:
        db.add(AuthToken(provider="codex", access_token=td.get("access_token"),
            refresh_token=td.get("refresh_token"), expires_at=expires_at, extra_data=td))
    await db.commit()
    ai_service.set_codex_token(td.get("access_token", ""))
    return RedirectResponse(url="/?auth=codex_success")

@router.delete("/codex/disconnect")
async def codex_disconnect(db: AsyncSession = Depends(get_db)):
    r = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    t = r.scalar_one_or_none()
    if t:
        await db.delete(t); await db.commit()
    ai_service.set_codex_token("")
    return {"success": True}

@router.post("/apikeys")
async def save_api_keys(payload: APIKeysUpdate, db: AsyncSession = Depends(get_db)):
    if payload.deepseek_api_key:
        r = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
        ex = r.scalar_one_or_none()
        if ex:
            ex.access_token = payload.deepseek_api_key
        else:
            db.add(AuthToken(provider="deepseek", access_token=payload.deepseek_api_key))
        ai_service.api_key = payload.deepseek_api_key
        await db.commit()
    if payload.bybit_api_key and payload.bybit_api_secret:
        try:
            with open(".env", "r") as f: content = f.read()
            for k, v in [("BYBIT_API_KEY", payload.bybit_api_key), ("BYBIT_API_SECRET", payload.bybit_api_secret)]:
                lines = content.split("\n"); found = False
                for i, line in enumerate(lines):
                    if line.startswith(f"{k}="):
                        lines[i] = f"{k}={v}"; found = True
                if not found: lines.append(f"{k}={v}")
                content = "\n".join(lines)
            with open(".env", "w") as f: f.write(content)
        except Exception as e:
            logger.warning(f"Could not update .env: {e}")
    return {"success": True, "message": "Saved. Bybit changes require restart."}

@router.post("/load-tokens")
async def load_tokens_endpoint(db: AsyncSession = Depends(get_db)):
    await _load_tokens_from_db(db)
    return {"loaded": True}

async def load_saved_tokens_internal():
    async with AsyncSessionLocal() as db:
        await _load_tokens_from_db(db)

async def _load_tokens_from_db(db: AsyncSession):
    r = await db.execute(select(AuthToken).where(AuthToken.provider == "codex"))
    c = r.scalar_one_or_none()
    if c and c.access_token and (not c.expires_at or c.expires_at > datetime.now(timezone.utc)):
        ai_service.set_codex_token(c.access_token)
    r2 = await db.execute(select(AuthToken).where(AuthToken.provider == "deepseek"))
    ds = r2.scalar_one_or_none()
    if ds and ds.access_token:
        ai_service.api_key = ds.access_token
