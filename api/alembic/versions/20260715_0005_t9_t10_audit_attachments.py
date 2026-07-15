"""T9 audit query and T10 attachment status.

Revision ID: 20260715_0005
Revises: 20260715_0004
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0005"
down_revision: str | None = "20260715_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    attachment_columns = {column["name"] for column in inspector.get_columns("attachment")}
    if "status" not in attachment_columns:
        op.add_column("attachment", sa.Column("status", sa.Text(), server_default=sa.text("'pending'"), nullable=False))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    attachment_columns = {column["name"] for column in inspector.get_columns("attachment")}
    if "status" in attachment_columns:
        op.drop_column("attachment", "status")
