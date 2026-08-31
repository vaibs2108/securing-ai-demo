"""
Securing AI — minimal session auth for the FastAPI backend.
Self-rolled HMAC-signed opaque token (no new dependency on pyjwt/itsdangerous).
Single-admin demo scope: token secret is generated fresh per process start
unless SESSION_SECRET is set in the environment, so restarting the backend
naturally invalidates old sessions.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import Header, HTTPException, status

_SECRET = (os.getenv("SESSION_SECRET") or secrets.token_hex(32)).encode()
_TTL_SECONDS = 60 * 60 * 12  # 12 hours


def issue_token(username: str, role: str) -> str:
    payload = {"u": username, "r": role, "exp": int(time.time()) + _TTL_SECONDS}
    raw = json.dumps(payload).encode()
    b64 = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(_SECRET, b64.encode(), hashlib.sha256).hexdigest()
    return f"{b64}.{sig}"


def verify_token(token: str) -> dict:
    try:
        b64, sig = token.split(".", 1)
        expected = hmac.new(_SECRET, b64.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            raise ValueError("bad signature")
        padded = b64 + "=" * (-len(b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()))
        if payload["exp"] < time.time():
            raise ValueError("expired")
        return payload
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired session")


def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    token = authorization[len("Bearer "):]
    return verify_token(token)
