from __future__ import annotations

import argparse

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db.models import AppUser
from app.db.session import SessionLocal


def upsert_user(username: str, password: str, role: str) -> AppUser:
    with SessionLocal() as db:
        user = db.scalar(select(AppUser).where(AppUser.username == username))
        if user is None:
            user = AppUser(
                username=username,
                password_hash=hash_password(password),
                role=role,
                token_version=0,
                failed_login_attempts=0,
                locked_until=None,
            )
            db.add(user)
        else:
            user.password_hash = hash_password(password)
            user.role = role
            user.failed_login_attempts = 0
            user.locked_until = None
            user.deleted_at = None
        db.commit()
        db.refresh(user)
        return user


def main() -> None:
    parser = argparse.ArgumentParser(description="Create or update an internal app user.")
    parser.add_argument("--username", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", required=True)
    args = parser.parse_args()

    user = upsert_user(args.username, args.password, args.role)
    print(f"upserted user {user.username} ({user.role}) id={user.id}")


if __name__ == "__main__":
    main()
