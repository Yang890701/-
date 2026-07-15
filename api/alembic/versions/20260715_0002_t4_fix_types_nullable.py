"""T4 fix: avg/special price -> NUMERIC; rent_confirm.billing_ym & tenant_contract.lease_start_date nullable.

Revision ID: 20260715_0002
Revises: 20260715_0001
Create Date: 2026-07-15
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260715_0002"
down_revision: str | None = "20260715_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 平均電價是小數(元/度)，原 Integer 會四捨五入 → 改 NUMERIC(10,4)
    op.alter_column(
        "avg_price", "price",
        existing_type=sa.Integer(), type_=sa.Numeric(10, 4),
        existing_nullable=False, postgresql_using="price::numeric(10,4)",
    )
    op.alter_column(
        "special_price", "price",
        existing_type=sa.Integer(), type_=sa.Numeric(10, 4),
        existing_nullable=False, postgresql_using="price::numeric(10,4)",
    )
    # 空帳單年月的繳租確認、空起租日的合約 應以 null 匯入而非丟棄
    op.alter_column("rent_confirm", "billing_ym", existing_type=sa.CHAR(6), nullable=True)
    op.drop_constraint("ck_rent_confirm_billing_ym", "rent_confirm", type_="check")
    op.create_check_constraint(
        "ck_rent_confirm_billing_ym", "rent_confirm",
        "billing_ym IS NULL OR billing_ym ~ '^[0-9]{6}$'",
    )
    op.alter_column("tenant_contract", "lease_start_date", existing_type=sa.Date(), nullable=True)


def downgrade() -> None:
    op.alter_column("tenant_contract", "lease_start_date", existing_type=sa.Date(), nullable=False)
    op.drop_constraint("ck_rent_confirm_billing_ym", "rent_confirm", type_="check")
    op.create_check_constraint(
        "ck_rent_confirm_billing_ym", "rent_confirm", "billing_ym ~ '^[0-9]{6}$'",
    )
    op.alter_column("rent_confirm", "billing_ym", existing_type=sa.CHAR(6), nullable=False)
    op.alter_column(
        "special_price", "price",
        existing_type=sa.Numeric(10, 4), type_=sa.Integer(),
        existing_nullable=False, postgresql_using="round(price)::integer",
    )
    op.alter_column(
        "avg_price", "price",
        existing_type=sa.Numeric(10, 4), type_=sa.Integer(),
        existing_nullable=False, postgresql_using="round(price)::integer",
    )
