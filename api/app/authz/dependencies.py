from __future__ import annotations

from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.auth.tokens import get_current_user
from app.db.models import AppUser


def is_admin(user: AppUser) -> bool:
    return user.role == "admin"


def is_manager(user: AppUser) -> bool:
    return user.role == "manager"


def require_roles(*roles: str) -> Callable[[AppUser], AppUser]:
    allowed = set(roles)

    def dependency(current_user: AppUser = Depends(get_current_user)) -> AppUser:
        if current_user.role not in allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
        return current_user

    return dependency
