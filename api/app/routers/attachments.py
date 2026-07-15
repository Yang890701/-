from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.tokens import get_current_user
from app.config import settings
from app.db.models import AppUser, Attachment
from app.db.session import get_db
from app.storage import LocalFolderStorage

router = APIRouter(prefix="/api/attachments", tags=["attachments"])

ALLOWED_MIME = {"image/jpeg", "image/png", "application/pdf"}
MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024
UPLOAD_TOKEN_SECONDS = 15 * 60
READ_TOKEN_SECONDS = 5 * 60
KIND_PATTERN = re.compile(r"[^a-zA-Z0-9_-]+")
EXTENSIONS = {"image/jpeg": ".jpg", "image/png": ".png", "application/pdf": ".pdf"}


class PresignRequest(BaseModel):
    kind: str = Field(min_length=1, max_length=64)
    mime: str
    size: int = Field(gt=0)


def _storage() -> LocalFolderStorage:
    return LocalFolderStorage(Path(__file__).resolve().parents[3] / "var" / "storage")


def _secret() -> bytes:
    _, secret = settings.active_jwt_key()
    return secret.encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _unb64(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _sign(payload: dict[str, Any]) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    return f"{body}.{signature}"


def _verify(token: str, purpose: str, attachment_id: int) -> dict[str, Any]:
    try:
        body, signature = token.split(".", 1)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token") from exc
    expected = _b64(hmac.new(_secret(), body.encode("ascii"), hashlib.sha256).digest())
    if not hmac.compare_digest(signature, expected):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token") from exc
    if payload.get("purpose") != purpose or payload.get("attachment_id") != attachment_id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid token")
    if int(payload.get("exp", 0)) < int(datetime.now(UTC).timestamp()):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Expired token")
    return payload


def _token(purpose: str, attachment: Attachment, ttl_seconds: int) -> str:
    return _sign(
        {
            "purpose": purpose,
            "attachment_id": attachment.id,
            "mime": attachment.mime,
            "size": attachment.size,
            "exp": int((datetime.now(UTC) + timedelta(seconds=ttl_seconds)).timestamp()),
        }
    )


def _clean_kind(kind: str) -> str:
    cleaned = KIND_PATTERN.sub("-", kind).strip("-").lower()
    return cleaned or "attachment"


def _object_key(kind: str, mime: str) -> str:
    return f"{_clean_kind(kind)}/{uuid4().hex}{EXTENSIONS[mime]}"


def _load_attachment(db: Session, attachment_id: int) -> Attachment:
    attachment = db.scalar(
        select(Attachment).where(Attachment.id == attachment_id, Attachment.deleted_at.is_(None))
    )
    if attachment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not found")
    return attachment


@router.post("/presign")
def presign_attachment(
    payload: PresignRequest,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    if payload.mime not in ALLOWED_MIME:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported MIME type")
    if payload.size > MAX_ATTACHMENT_SIZE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is too large")

    attachment = Attachment(
        kind=payload.kind,
        mime=payload.mime,
        size=payload.size,
        object_key=_object_key(payload.kind, payload.mime),
        status="pending",
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    token = _token("upload", attachment, UPLOAD_TOKEN_SECONDS)
    return {
        "attachment_id": attachment.id,
        "upload_url": f"/api/attachments/{attachment.id}/upload?token={token}",
    }


@router.put("/{attachment_id}/upload")
@router.post("/{attachment_id}/upload")
async def upload_attachment(
    attachment_id: int,
    request: Request,
    token: str,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    del current_user
    attachment = _load_attachment(db, attachment_id)
    _verify(token, "upload", attachment.id)
    if attachment.status == "ready":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is already uploaded")

    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type != attachment.mime:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="MIME type does not match presign"
        )

    body = await request.body()
    if len(body) > MAX_ATTACHMENT_SIZE or len(body) > attachment.size:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment is too large")
    if not body:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Attachment body is empty")

    _storage().save(attachment.object_key, body)
    attachment.status = "ready"
    attachment.size = len(body)
    db.commit()
    return {"attachment_id": attachment.id, "status": attachment.status, "size": attachment.size}


@router.get("/{attachment_id}")
def get_attachment(
    attachment_id: int,
    current_user: AppUser = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, int | str]:
    del current_user
    attachment = _load_attachment(db, attachment_id)
    if attachment.status != "ready":
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not ready")
    token = _token("read", attachment, READ_TOKEN_SECONDS)
    return {
        "attachment_id": attachment.id,
        "mime": attachment.mime,
        "size": attachment.size,
        "status": attachment.status,
        "read_url": f"/api/attachments/{attachment.id}/download?token={token}",
    }


@router.get("/{attachment_id}/download")
def download_attachment(attachment_id: int, token: str, db: Session = Depends(get_db)) -> Response:
    attachment = _load_attachment(db, attachment_id)
    _verify(token, "read", attachment.id)
    if attachment.status != "ready" or not _storage().exists(attachment.object_key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Attachment not ready")
    return Response(content=_storage().read(attachment.object_key), media_type=attachment.mime)
