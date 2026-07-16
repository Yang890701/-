"""Portal home tables (dynamic homepage: groups/categories/links/notices).

Revision ID: 20260716_0006
Revises: 20260715_0005
Create Date: 2026-07-16
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "20260716_0006"
down_revision: str | None = "20260715_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _core_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "portal_link_group",
        *_core_columns(),
        sa.Column("group_code", sa.Text(), nullable=False),
        sa.Column("group_name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        comment="入口首頁-連結群組",
    )
    op.create_index(
        "uq_portal_link_group_code_active", "portal_link_group", ["group_code"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "portal_link_category",
        *_core_columns(),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("group_code", sa.Text(), nullable=False),
        sa.Column("category_name", sa.Text(), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        comment="入口首頁-連結分類",
    )
    op.create_index(
        "uq_portal_link_category_code_active", "portal_link_category", ["category_code"],
        unique=True, postgresql_where=sa.text("deleted_at IS NULL"),
    )

    op.create_table(
        "portal_link",
        *_core_columns(),
        sa.Column("category_code", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_new", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        comment="入口首頁-連結",
    )

    op.create_table(
        "portal_notice",
        *_core_columns(),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("pinned", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("sort_order", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        comment="入口首頁-公告",
    )

    # --- seed content (連結指向新系統原生頁) ---
    op.execute(
        """
        INSERT INTO portal_link_group (group_code, group_name, sort_order) VALUES
        ('forms', '表單作業', 10),
        ('data', '資料查詢與後台', 20);
        """
    )
    op.execute(
        """
        INSERT INTO portal_link_category (category_code, group_code, category_name, sort_order) VALUES
        ('master', 'forms', '主檔管理', 10),
        ('elec', 'forms', '電費作業', 20),
        ('query', 'data', '資料查詢', 10);
        """
    )
    op.execute(
        """
        INSERT INTO portal_link (category_code, title, url, description, is_new, sort_order) VALUES
        ('master', '案場管理', '/master/site', '案場建立/更新/停用', false, 10),
        ('master', '電號管理', '/master/meter', '電號建立/更新/停用', false, 20),
        ('master', '房號管理', '/master/room', '房號建立/更新/停用', false, 30),
        ('elec', '平均電價上傳', '/upload/price', '各期台電平均電價上傳', false, 10),
        ('elec', '房號度數上傳', '/upload/reading', '各期房號度數上傳', false, 20),
        ('elec', '繳租確認（電費試算/發布）', '/billing', '電費試算→核准→發布', true, 30),
        ('query', '通用資料檢視', '/data', '選任一張表→篩選→匯出 Excel', false, 10),
        ('query', '稽核紀錄', '/audit', '系統操作紀錄查詢', false, 20);
        """
    )
    op.execute(
        """
        INSERT INTO portal_notice (title, content, pinned, sort_order) VALUES
        ('歡迎使用好室包租代管系統', NULL, true, 10),
        ('【置頂】若需修改房號名稱，請通知後端人員', NULL, true, 20),
        ('例外費用管理功能開發中，敬請期待', NULL, false, 30);
        """
    )


def downgrade() -> None:
    op.drop_table("portal_notice")
    op.drop_table("portal_link")
    op.drop_index("uq_portal_link_category_code_active", table_name="portal_link_category")
    op.drop_table("portal_link_category")
    op.drop_index("uq_portal_link_group_code_active", table_name="portal_link_group")
    op.drop_table("portal_link_group")
