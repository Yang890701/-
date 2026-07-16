from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.db.models import (
    AppUser,
    PortalLink,
    PortalLinkCategory,
    PortalLinkGroup,
    PortalNotice,
)
from app.db.session import get_db

router = APIRouter(prefix="/api/portal", tags=["portal"])


@router.get("")
def get_portal(
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """入口首頁內容（只讀）：群組→分類→連結 + 公告。所有登入者可見。"""
    del current_user

    groups = db.scalars(
        select(PortalLinkGroup)
        .where(PortalLinkGroup.deleted_at.is_(None), PortalLinkGroup.is_enabled.is_(True))
        .order_by(PortalLinkGroup.sort_order, PortalLinkGroup.id)
    ).all()
    categories = db.scalars(
        select(PortalLinkCategory)
        .where(PortalLinkCategory.deleted_at.is_(None), PortalLinkCategory.is_enabled.is_(True))
        .order_by(PortalLinkCategory.sort_order, PortalLinkCategory.id)
    ).all()
    links = db.scalars(
        select(PortalLink)
        .where(PortalLink.deleted_at.is_(None), PortalLink.is_enabled.is_(True))
        .order_by(PortalLink.sort_order, PortalLink.id)
    ).all()
    notices = db.scalars(
        select(PortalNotice)
        .where(PortalNotice.deleted_at.is_(None), PortalNotice.is_enabled.is_(True))
        .order_by(PortalNotice.pinned.desc(), PortalNotice.sort_order, PortalNotice.id)
    ).all()

    links_by_cat: dict[str, list[dict[str, Any]]] = {}
    for link in links:
        links_by_cat.setdefault(link.category_code, []).append(
            {
                "title": link.title,
                "url": link.url,
                "description": link.description,
                "is_new": link.is_new,
            }
        )

    cats_by_group: dict[str, list[dict[str, Any]]] = {}
    for cat in categories:
        cats_by_group.setdefault(cat.group_code, []).append(
            {
                "category_code": cat.category_code,
                "category_name": cat.category_name,
                "links": links_by_cat.get(cat.category_code, []),
            }
        )

    return {
        "groups": [
            {
                "group_code": g.group_code,
                "group_name": g.group_name,
                "categories": cats_by_group.get(g.group_code, []),
            }
            for g in groups
        ],
        "notices": [
            {"title": n.title, "content": n.content, "pinned": n.pinned}
            for n in notices
        ],
    }
