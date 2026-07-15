from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.passwords import verify_password
from app.auth.refresh import hash_refresh_token, new_refresh_token, refresh_expires_at
from app.auth.tokens import create_access_token, get_current_user
from app.config import settings
from app.db.models import AppUser, AuditLog, RefreshSession
from app.db.session import get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


def user_payload(user: AppUser) -> dict[str, int | str]:
    return {"id": user.id, "username": user.username, "role": user.role}


def set_refresh_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.auth_refresh_cookie_name,
        token,
        max_age=settings.refresh_token_ttl_seconds,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/",
    )


def create_refresh_session(db: Session, user: AppUser, request: Request) -> str:
    token = new_refresh_token()
    db.add(
        RefreshSession(
            user_id=user.id,
            token_hash=hash_refresh_token(token),
            expires_at=refresh_expires_at(),
            user_agent=request.headers.get("user-agent"),
        )
    )
    return token


def locked_response(user: AppUser) -> None:
    now = datetime.now(UTC)
    if user.locked_until and user.locked_until > now:
        raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is locked")


@router.post("/login")
def login(payload: LoginRequest, request: Request, response: Response, db: Session = Depends(get_db)) -> dict:
    user = db.scalar(
        select(AppUser).where(AppUser.username == payload.username, AppUser.deleted_at.is_(None))
    )
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    locked_response(user)
    if not verify_password(payload.password, user.password_hash):
        user.failed_login_attempts += 1
        if user.failed_login_attempts >= settings.lockout_threshold:
            user.locked_until = datetime.now(UTC) + timedelta(seconds=settings.lockout_window_seconds)
            db.commit()
            raise HTTPException(status_code=status.HTTP_423_LOCKED, detail="Account is locked")
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")

    user.failed_login_attempts = 0
    user.locked_until = None
    refresh_token = create_refresh_session(db, user, request)
    db.add(AuditLog(actor=user.id, action="login"))
    db.commit()
    set_refresh_cookie(response, refresh_token)
    return {
        "access_token": create_access_token(user),
        "token_type": "bearer",
        "user": user_payload(user),
    }


@router.post("/refresh")
def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_refresh_cookie_name),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing refresh token")
    token_hash = hash_refresh_token(refresh_token)
    session = db.scalar(
        select(RefreshSession).where(
            RefreshSession.token_hash == token_hash,
            RefreshSession.deleted_at.is_(None),
        )
    )
    now = datetime.now(UTC)
    if session is None or session.revoked_at is not None or session.expires_at <= now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")
    user = db.scalar(select(AppUser).where(AppUser.id == session.user_id, AppUser.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    session.revoked_at = now
    new_token = create_refresh_session(db, user, request)
    db.commit()
    set_refresh_cookie(response, new_token)
    return {"access_token": create_access_token(user), "token_type": "bearer"}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.auth_refresh_cookie_name),
    db: Session = Depends(get_db),
) -> Response:
    if refresh_token:
        session = db.scalar(
            select(RefreshSession).where(
                RefreshSession.token_hash == hash_refresh_token(refresh_token),
                RefreshSession.deleted_at.is_(None),
            )
        )
        if session and session.revoked_at is None:
            session.revoked_at = datetime.now(UTC)
            db.commit()
    response.delete_cookie(settings.auth_refresh_cookie_name, path="/")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me")
def me(current_user: AppUser = Depends(get_current_user)) -> dict[str, int | str]:
    return user_payload(current_user)
