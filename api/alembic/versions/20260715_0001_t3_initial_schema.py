"""T3 initial PostgreSQL schema.

Revision ID: 20260715_0001
Revises:
Create Date: 2026-07-15
"""

from collections.abc import Sequence

from alembic import op

from app.db.models import Base


revision: str = "20260715_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()

    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist")
    Base.metadata.create_all(bind=bind)

    op.execute(
        """
        ALTER TABLE room_meter_assignment
        ADD CONSTRAINT room_meter_assignment_no_overlap
        EXCLUDE USING gist (
            room_id WITH =,
            meter_category WITH =,
            int4range(
                effective_from_ym::int,
                COALESCE(effective_to_ym::int, 999999),
                '[]'
            ) WITH &&
        )
        WHERE (deleted_at IS NULL)
        """
    )

    op.execute(
        """
        CREATE VIEW tenant_current AS
        SELECT *
        FROM (
            SELECT
                tenant_contract.*,
                row_number() OVER (
                    PARTITION BY room_id
                    ORDER BY lease_start_date DESC, id DESC
                ) AS rn
            FROM tenant_contract
            WHERE deleted_at IS NULL
              AND lease_start_date <= CURRENT_DATE
              AND (lease_end_date IS NULL OR lease_end_date >= CURRENT_DATE)
        ) latest
        WHERE rn = 1
        """
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.execute("DROP VIEW IF EXISTS tenant_current")
    op.execute(
        """
        ALTER TABLE IF EXISTS room_meter_assignment
        DROP CONSTRAINT IF EXISTS room_meter_assignment_no_overlap
        """
    )
    Base.metadata.drop_all(bind=bind)
