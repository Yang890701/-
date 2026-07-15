from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AppUser
from app.db.session import get_db

bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(user: AppUser, ttl_seconds: int | None = None) -> str:
    kid, secret = settings.active_jwt_key()
    expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds or settings.access_token_ttl_seconds)
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "token_version": user.token_version,
        "exp": expires_at,
    }
    return jwt.encode(payload, secret, algorithm="HS256", headers={"kid": kid})


def decode_access_token(token: str) -> dict:
    try:
        header = jwt.get_unverified_header(token)
        kid = header.get("kid")
        if not kid:
            raise jwt.InvalidTokenError("missing kid")
        keys = settings.jwt_key_map()
        secret = keys.get(kid)
        if not secret:
            raise jwt.InvalidTokenError("unknown kid")
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> AppUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing bearer token")
    claims = decode_access_token(credentials.credentials)
    try:
        user_id = int(claims["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token") from exc
    user = db.scalar(select(AppUser).where(AppUser.id == user_id, AppUser.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    if claims.get("token_version") != user.token_version:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid access token")
    return user
