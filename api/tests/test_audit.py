import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "1200")
os.environ.setdefault("REFRESH_TOKEN_TTL_SECONDS", "1209600")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.db.models import AppUser, AuditLog, Room, Site
from app.db.session import get_db
from app.main import app
from app.meta.seed import seed_metadata


class AuditApiTest(unittest.TestCase):
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
        self.prefix = f"audit_{uuid4().hex}"
        seed_metadata(self.session, actor="test")
        self.admin = self.create_user("admin")
        self.staff = self.create_user("staff")
        self.site = Site(site_code=f"{self.prefix}_site", name="Audit Site")
        self.session.add(self.site)
        self.session.flush()
        self.room = Room(site_id=self.site.id, room_code=f"{self.prefix}_101", room_name="Audit Room")
        self.session.add(self.room)
        self.session.commit()

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.session.close()
        self.transaction.rollback()
        self.connection.close()

    def create_user(self, role: str) -> AppUser:
        user = AppUser(
            username=f"{self.prefix}_{role}",
            password_hash=hash_password("password"),
            role=role,
            token_version=0,
        )
        self.session.add(user)
        self.session.flush()
        return user

    def auth_headers(self, user: AppUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user)}"}

    def test_audit_query_returns_rows_and_is_itself_audited(self) -> None:
        self.session.add(
            AuditLog(actor=self.admin.id, action="query", table_code="room", filters={}, row_count=1)
        )
        self.session.commit()
        before = self.session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "audit_query")
        )

        response = self.client.get("/api/audit?action=query", headers=self.auth_headers(self.admin))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreaterEqual(body["total"], 1)
        self.assertEqual(body["rows"][0]["action"], "query")
        after = self.session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.action == "audit_query")
        )
        self.assertEqual(after, before + 1)

    def test_audit_query_is_admin_only(self) -> None:
        response = self.client.get("/api/audit", headers=self.auth_headers(self.staff))

        self.assertEqual(response.status_code, 403)

    def test_login_and_data_query_write_audit_rows(self) -> None:
        login = self.client.post(
            "/api/auth/login",
            json={"username": self.admin.username, "password": "password"},
        )
        query = self.client.post(
            "/api/data/room/query",
            json={
                "filters": [{"col": "room_code", "op": "eq", "val": self.room.room_code}],
                "sort": [],
                "page": 1,
                "size": 50,
            },
            headers=self.auth_headers(self.admin),
        )

        self.assertEqual(login.status_code, 200)
        self.assertEqual(query.status_code, 200)
        login_audit = self.session.scalar(
            select(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.action == "login")
            .order_by(AuditLog.id.desc())
        )
        query_audit = self.session.scalar(
            select(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.action == "query")
            .order_by(AuditLog.id.desc())
        )
        self.assertIsNotNone(login_audit)
        self.assertEqual(query_audit.table_code, "room")
        self.assertEqual(query_audit.row_count, 1)


if __name__ == "__main__":
    unittest.main()
