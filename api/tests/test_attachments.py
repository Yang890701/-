import os
import unittest
from pathlib import Path
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "1200")
os.environ.setdefault("REFRESH_TOKEN_TTL_SECONDS", "1209600")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.db.models import AppUser, Attachment
from app.db.session import get_db
from app.main import app

STORAGE_ROOT = Path(__file__).resolve().parents[2] / "var" / "storage"


class AttachmentApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise unittest.SkipTest("DATABASE_URL is not set")
        cls.engine = create_engine(database_url, future=True)
        cls.SessionLocal = sessionmaker(expire_on_commit=False, future=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.connection = self.engine.connect()
        self.transaction = self.connection.begin()
        self.session = self.SessionLocal(bind=self.connection)
        self.prefix = f"attach_{uuid4().hex}"
        self.user = AppUser(
            username=f"{self.prefix}_admin",
            password_hash=hash_password("password"),
            role="admin",
            token_version=0,
        )
        self.session.add(self.user)
        self.session.commit()

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        for attachment in self.session.scalars(
            select(Attachment).where(Attachment.kind.like(f"{self.prefix}%"))
        ).all():
            path = STORAGE_ROOT / attachment.object_key
            if path.exists():
                path.unlink()
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def auth_headers(self, content_type: str | None = None) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {create_access_token(self.user)}"}
        if content_type:
            headers["Content-Type"] = content_type
        return headers

    def test_presign_rejects_bad_mime_and_oversize(self) -> None:
        bad_mime = self.client.post(
            "/api/attachments/presign",
            json={"kind": self.prefix, "mime": "text/plain", "size": 10},
            headers=self.auth_headers(),
        )
        oversize = self.client.post(
            "/api/attachments/presign",
            json={"kind": self.prefix, "mime": "image/png", "size": 10 * 1024 * 1024 + 1},
            headers=self.auth_headers(),
        )

        self.assertEqual(bad_mime.status_code, 400)
        self.assertEqual(oversize.status_code, 400)

    def test_presign_upload_get_roundtrip_returns_signed_url_not_raw_path(self) -> None:
        content = b"%PDF-1.4\nbody\n"
        presign = self.client.post(
            "/api/attachments/presign",
            json={"kind": self.prefix, "mime": "application/pdf", "size": len(content)},
            headers=self.auth_headers(),
        )
        self.assertEqual(presign.status_code, 200)
        body = presign.json()
        self.assertIn("token=", body["upload_url"])
        self.assertNotIn("var/storage", body["upload_url"])

        upload = self.client.put(
            body["upload_url"], content=content, headers=self.auth_headers("application/pdf")
        )
        self.assertEqual(upload.status_code, 200)
        self.assertEqual(upload.json()["status"], "ready")

        metadata = self.client.get(f"/api/attachments/{body['attachment_id']}", headers=self.auth_headers())
        self.assertEqual(metadata.status_code, 200)
        read_url = metadata.json()["read_url"]
        self.assertIn("token=", read_url)
        self.assertNotIn("var/storage", read_url)

        download = self.client.get(read_url)
        self.assertEqual(download.status_code, 200)
        self.assertEqual(download.content, content)
        self.assertEqual(download.headers["content-type"], "application/pdf")

    def test_upload_rejects_bad_token_oversize_and_mime(self) -> None:
        presign = self.client.post(
            "/api/attachments/presign",
            json={"kind": self.prefix, "mime": "image/png", "size": 4},
            headers=self.auth_headers(),
        )
        upload_url = presign.json()["upload_url"]

        bad_token = self.client.put(
            upload_url.replace("token=", "token=bad"),
            content=b"1234",
            headers=self.auth_headers("image/png"),
        )
        bad_mime = self.client.put(upload_url, content=b"1234", headers=self.auth_headers("application/pdf"))
        oversize = self.client.put(upload_url, content=b"12345", headers=self.auth_headers("image/png"))

        self.assertEqual(bad_token.status_code, 403)
        self.assertEqual(bad_mime.status_code, 400)
        self.assertEqual(oversize.status_code, 400)


if __name__ == "__main__":
    unittest.main()
