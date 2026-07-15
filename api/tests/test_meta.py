import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, delete, func, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "1200")
os.environ.setdefault("REFRESH_TOKEN_TTL_SECONDS", "1209600")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.db.models import AppUser, ColumnMeta, TableMeta
from app.db.session import get_db
from app.main import app
from app.meta.resolver import MetadataResolutionError, resolve_query_plan
from app.meta.seed import seed_metadata


class MetadataLayerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise unittest.SkipTest("DATABASE_URL is not set")
        cls.engine = create_engine(database_url, future=True)
        cls.SessionLocal = sessionmaker(cls.engine, expire_on_commit=False, future=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()

    def setUp(self) -> None:
        self.session = self.SessionLocal()
        self.username = f"meta_{uuid4().hex}"

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)
        seed_metadata(self.session, actor="test")
        self.staff = self.create_user("staff")
        self.admin = self.create_user("admin")

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.session.rollback()
        self.session.execute(delete(AppUser).where(AppUser.username.like(f"{self.username}%")))
        self.session.commit()
        self.session.close()

    def create_user(self, role: str) -> AppUser:
        user = AppUser(
            username=f"{self.username}_{role}",
            password_hash=hash_password("password"),
            role=role,
            token_version=0,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def auth_headers(self, user: AppUser) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user)}"}

    def test_resolver_rejects_unregistered_table_column_and_operator(self) -> None:
        with self.assertRaises(MetadataResolutionError):
            resolve_query_plan(self.session, "not_registered", ["room_code"], [])

        with self.assertRaises(MetadataResolutionError):
            resolve_query_plan(self.session, "room", ["not_registered"], [])

        with self.assertRaises(MetadataResolutionError):
            resolve_query_plan(
                self.session,
                "room",
                ["room_code"],
                [{"col": "room_code", "op": "range", "val": ["A", "Z"]}],
            )

    def test_role_masking_hides_sensitive_columns_from_staff_but_not_admin(self) -> None:
        staff_response = self.client.get(
            "/api/meta/tables/tenant_contract/columns",
            headers=self.auth_headers(self.staff),
        )
        admin_response = self.client.get(
            "/api/meta/tables/tenant_contract/columns",
            headers=self.auth_headers(self.admin),
        )

        self.assertEqual(staff_response.status_code, 200)
        self.assertEqual(admin_response.status_code, 200)
        staff_codes = {column["code"] for column in staff_response.json()}
        admin_codes = {column["code"] for column in admin_response.json()}
        self.assertNotIn("contact_phone", staff_codes)
        self.assertNotIn("rent", staff_codes)
        self.assertIn("contact_phone", admin_codes)
        self.assertIn("rent", admin_codes)

    def test_seed_is_idempotent(self) -> None:
        first_tables = self.session.scalar(select(func.count()).select_from(TableMeta))
        first_columns = self.session.scalar(select(func.count()).select_from(ColumnMeta))

        seed_metadata(self.session, actor="test")

        second_tables = self.session.scalar(select(func.count()).select_from(TableMeta))
        second_columns = self.session.scalar(select(func.count()).select_from(ColumnMeta))
        self.assertEqual(second_tables, first_tables)
        self.assertEqual(second_columns, first_columns)


if __name__ == "__main__":
    unittest.main()
