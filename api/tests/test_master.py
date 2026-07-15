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


class MasterApiTest(unittest.TestCase):
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
        self.prefix = f"master_{uuid4().hex}"
        seed_metadata(self.session, actor="test")
        self.admin = self.create_user("admin")
        self.staff = self.create_user("staff")
        self.site = Site(site_code=f"{self.prefix}_site", name="Master Site")
        self.session.add(self.site)
        self.session.flush()
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

    def room_payload(self, room_code: str | None = None) -> dict[str, object]:
        return {
            "site_id": self.site.id,
            "room_code": room_code or f"{self.prefix}_101",
            "room_name": "Room 101",
            "meter_id": None,
            "management_type": "self",
            "management_contact": "Manager",
            "billing_mode": "standard",
        }

    def create_room(self, payload: dict[str, object] | None = None):
        return self.client.post(
            "/api/master/room",
            json=payload or self.room_payload(),
            headers=self.auth_headers(self.admin),
        )

    def test_create_room_under_existing_site_appears_in_list(self) -> None:
        response = self.create_room()

        self.assertEqual(response.status_code, 201)
        created = response.json()
        list_response = self.client.get("/api/master/room", headers=self.auth_headers(self.admin))

        self.assertEqual(list_response.status_code, 200)
        room_ids = [row["id"] for row in list_response.json()["rows"]]
        self.assertIn(created["id"], room_ids)

    def test_create_room_referencing_nonexistent_site_returns_400(self) -> None:
        payload = self.room_payload(f"{self.prefix}_bad_site")
        payload["site_id"] = 999_999_999

        response = self.create_room(payload)

        self.assertEqual(response.status_code, 400)

    def test_duplicate_room_natural_key_returns_409(self) -> None:
        payload = self.room_payload(f"{self.prefix}_dupe")
        first = self.create_room(payload)
        duplicate = self.create_room(payload)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("自然鍵重複", duplicate.json()["detail"])

    def test_soft_delete_room_hides_default_list_but_include_inactive_shows_it(self) -> None:
        created = self.create_room(self.room_payload(f"{self.prefix}_inactive")).json()

        delete_response = self.client.delete(
            f"/api/master/room/{created['id']}",
            headers=self.auth_headers(self.admin),
        )
        default_list = self.client.get("/api/master/room", headers=self.auth_headers(self.admin))
        history_list = self.client.get(
            "/api/master/room?include_inactive=true",
            headers=self.auth_headers(self.admin),
        )

        self.assertEqual(delete_response.status_code, 200)
        self.assertNotIn(created["id"], [row["id"] for row in default_list.json()["rows"]])
        self.assertIn(created["id"], [row["id"] for row in history_list.json()["rows"]])
        inactive_row = next(row for row in history_list.json()["rows"] if row["id"] == created["id"])
        self.assertIsNotNone(inactive_row["deleted_at"])

    def test_staff_create_returns_403(self) -> None:
        response = self.client.post(
            "/api/master/room",
            json=self.room_payload(f"{self.prefix}_staff"),
            headers=self.auth_headers(self.staff),
        )

        self.assertEqual(response.status_code, 403)

    def test_successful_mutations_write_audit_rows(self) -> None:
        before = self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "room")
        )

        created = self.create_room(self.room_payload(f"{self.prefix}_audit")).json()
        update_payload = self.room_payload(f"{self.prefix}_audit")
        update_payload["room_name"] = "Room 101 updated"
        update_response = self.client.put(
            f"/api/master/room/{created['id']}",
            json=update_payload,
            headers=self.auth_headers(self.admin),
        )
        delete_response = self.client.delete(
            f"/api/master/room/{created['id']}",
            headers=self.auth_headers(self.admin),
        )

        self.assertEqual(update_response.status_code, 200)
        self.assertEqual(delete_response.status_code, 200)
        after = self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "room")
        )
        self.assertEqual(after, before + 3)
        actions = self.session.scalars(
            select(AuditLog.action)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "room")
            .order_by(AuditLog.id.desc())
            .limit(3)
        ).all()
        self.assertEqual(actions, ["master_delete", "master_update", "master_create"])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(Room).where(Room.id == created["id"])),
            1,
        )


if __name__ == "__main__":
    unittest.main()
