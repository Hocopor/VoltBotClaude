import hashlib
import hmac
import json
import secrets
import time
from base64 import urlsafe_b64decode, urlsafe_b64encode
from typing import Optional

import bcrypt
from fastapi import Cookie, HTTPException, Request, WebSocket, status

from app.config import settings


SESSION_COOKIE_NAME = "voltage_session"
MAX_BCRYPT_PASSWORD_BYTES = 72


def hash_password(password: str) -> str:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        raise ValueError("Password must be 72 bytes or fewer for bcrypt")
    return bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    password_bytes = password.encode("utf-8")
    if len(password_bytes) > MAX_BCRYPT_PASSWORD_BYTES:
        return False
    return bcrypt.checkpw(password_bytes, password_hash.encode("utf-8"))


def _session_secret() -> bytes:
    return settings.SECRET_KEY.encode("utf-8")


def _b64encode(data: bytes) -> str:
    return urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return urlsafe_b64decode((data + padding).encode("ascii"))


def create_session_token(login: str) -> str:
    payload = {
        "sub": login,
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.APP_AUTH_SESSION_TTL_HOURS * 3600,
        "nonce": secrets.token_urlsafe(8),
    }
    payload_bytes = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")
    payload_part = _b64encode(payload_bytes)
    signature = hmac.new(_session_secret(), payload_part.encode("utf-8"), hashlib.sha256).digest()
    return f"{payload_part}.{_b64encode(signature)}"


def decode_session_token(token: str) -> Optional[dict]:
    try:
        payload_part, signature_part = token.split(".", 1)
        expected_signature = hmac.new(
            _session_secret(), payload_part.encode("utf-8"), hashlib.sha256
        ).digest()
        provided_signature = _b64decode(signature_part)
        if not hmac.compare_digest(expected_signature, provided_signature):
            return None
        payload = json.loads(_b64decode(payload_part).decode("utf-8"))
        if payload.get("exp", 0) < int(time.time()):
            return None
        if payload.get("sub") != settings.APP_AUTH_LOGIN:
            return None
        return payload
    except Exception:
        return None


def session_cookie_settings() -> dict:
    return {
        "key": SESSION_COOKIE_NAME,
        "httponly": True,
        "secure": settings.APP_AUTH_COOKIE_SECURE,
        "samesite": "lax",
        "max_age": settings.APP_AUTH_SESSION_TTL_HOURS * 3600,
        "path": "/",
    }


def get_authenticated_login_from_request(request: Request) -> Optional[str]:
    token = request.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token) if token else None
    return payload.get("sub") if payload else None


def get_authenticated_login_from_websocket(websocket: WebSocket) -> Optional[str]:
    token = websocket.cookies.get(SESSION_COOKIE_NAME)
    payload = decode_session_token(token) if token else None
    return payload.get("sub") if payload else None


async def require_authenticated_user(
    voltage_session: Optional[str] = Cookie(default=None, alias=SESSION_COOKIE_NAME),
) -> str:
    payload = decode_session_token(voltage_session) if voltage_session else None
    if not payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return payload["sub"]
