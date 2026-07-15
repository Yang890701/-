"""T5 internal authentication.

Revision ID: 20260715_0003
Revises: 20260715_0002
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0003"
down_revision: str | None = "20260715_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    app_user_columns = {column["name"] for column in inspector.get_columns("app_user")}

    if "failed_login_attempts" not in app_user_columns:
        op.add_column(
            "app_user",
            sa.Column("failed_login_attempts", sa.Integer(), server_default=sa.text("0"), nullable=False),
        )
    if "locked_until" not in app_user_columns:
        op.add_column("app_user", sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True))

    if "refresh_session" not in inspector.get_table_names():
        op.create_table(
            "refresh_session",
            sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("app_user.id"), nullable=False),
            sa.Column("token_hash", sa.Text(), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("user_agent", sa.Text(), nullable=True),
        )
        op.create_index("uq_refresh_session_token_hash", "refresh_session", ["token_hash"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "refresh_session" in inspector.get_table_names():
        op.drop_index("uq_refresh_session_token_hash", table_name="refresh_session")
        op.drop_table("refresh_session")

    app_user_columns = {column["name"] for column in inspector.get_columns("app_user")}
    if "locked_until" in app_user_columns:
        op.drop_column("app_user", "locked_until")
    if "failed_login_attempts" in app_user_columns:
        op.drop_column("app_user", "failed_login_attempts")
