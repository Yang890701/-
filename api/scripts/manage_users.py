"""好室 使用者管理小工具（部署／維運用）。

從環境變數 DATABASE_URL 讀連線字串。請於 api/ 目錄下以模組方式執行：

    python -m scripts.manage_users set-password --username admin --password 'NEW_STRONG_PW'
    python -m scripts.manage_users create --username demo --password 'DEMO_PW' --role staff
    python -m scripts.manage_users list

角色說明：admin / manager / accounting / staff
（staff 依 column_meta 設定看不到 電話／租金／繳費 等敏感欄）。
"""

from __future__ import annotations

import argparse

from sqlalchemy import select

from app.auth.passwords import hash_password
from app.db.models import AppUser
from app.db.session import SessionLocal


def _set_password(username: str, password: str) -> None:
    with SessionLocal() as db:
        user = db.scalar(
            select(AppUser).where(AppUser.username == username, AppUser.deleted_at.is_(None))
        )
        if user is None:
            raise SystemExit(f"找不到使用者：{username}")
        user.password_hash = hash_password(password)
        # 讓既有 access/refresh 失效並清除鎖定
        user.token_version = (user.token_version or 0) + 1
        user.failed_login_attempts = 0
        user.locked_until = None
        db.commit()
        print(f"已更新密碼並解鎖：{username}（role={user.role}）")


def _create(username: str, password: str, role: str, readonly: bool) -> None:
    with SessionLocal() as db:
        existing = db.scalar(
            select(AppUser).where(AppUser.username == username, AppUser.deleted_at.is_(None))
        )
        if existing is not None:
            raise SystemExit(f"使用者已存在：{username}")
        db.add(
            AppUser(
                username=username,
                password_hash=hash_password(password),
                role=role,
                is_readonly=readonly,
            )
        )
        db.commit()
        print(f"已建立使用者：{username}（role={role}, readonly={readonly}）")


def _list() -> None:
    with SessionLocal() as db:
        users = db.scalars(
            select(AppUser).where(AppUser.deleted_at.is_(None)).order_by(AppUser.id)
        ).all()
        for u in users:
            print(
                f"#{u.id} {u.username} role={u.role} "
                f"readonly={u.is_readonly} locked_until={u.locked_until}"
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="好室使用者管理")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_set = sub.add_parser("set-password", help="設定既有使用者密碼並解鎖")
    p_set.add_argument("--username", required=True)
    p_set.add_argument("--password", required=True)

    p_new = sub.add_parser("create", help="建立新使用者")
    p_new.add_argument("--username", required=True)
    p_new.add_argument("--password", required=True)
    p_new.add_argument(
        "--role", required=True, choices=["admin", "manager", "accounting", "staff"]
    )
    p_new.add_argument("--readonly", action="store_true", help="設為唯讀帳號")

    sub.add_parser("list", help="列出使用者")

    args = parser.parse_args()
    if args.cmd == "set-password":
        _set_password(args.username, args.password)
    elif args.cmd == "create":
        _create(args.username, args.password, args.role, args.readonly)
    elif args.cmd == "list":
        _list()


if __name__ == "__main__":
    main()
