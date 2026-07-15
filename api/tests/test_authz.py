import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "1200")
os.environ.setdefault("REFRESH_TOKEN_TTL_SECONDS", "1209600")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.authz.dependencies import require_roles
from app.authz.fields import allowed_columns, mask_row
from app.authz.scopes import apply_scope, scope_predicate
from app.db.models import AppUser, RentConfirm, Room, Site, UserScope
from app.db.session import get_db
from app.meta.seed import seed_metadata


class AuthorizationLayerTest(unittest.TestCase):
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
        self.prefix = f"authz_{uuid4().hex}"
        seed_metadata(self.session, actor="test")

        self.admin = self.create_user("admin")
        self.staff = self.create_user("staff")
        self.site_a = Site(site_code=f"{self.prefix}_A", name="Site A")
        self.site_b = Site(site_code=f"{self.prefix}_B", name="Site B")
        self.session.add_all([self.site_a, self.site_b])
        self.session.flush()
        self.room_a = Room(site_id=self.site_a.id, room_code=f"{self.prefix}_101")
        self.room_b = Room(site_id=self.site_b.id, room_code=f"{self.prefix}_201")
        self.session.add_all([self.room_a, self.room_b])
        self.session.flush()
        self.confirm_a = RentConfirm(
            room_id=self.room_a.id,
            billing_ym="202607",
            charge_type="rent",
            run_version=1,
            status="draft",
            rent_amount=1000,
        )
        self.confirm_b = RentConfirm(
            room_id=self.room_b.id,
            billing_ym="202607",
            charge_type="rent",
            run_version=1,
            status="draft",
            rent_amount=2000,
        )
        self.session.add_all([self.confirm_a, self.confirm_b])
        self.session.flush()
        self.session.add(UserScope(user_id=self.staff.id, scope_type="site", scope_value=str(self.site_a.id)))
        self.session.commit()

    def tearDown(self) -> None:
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

    def test_admin_scope_predicate_is_none_and_sees_all_rooms(self) -> None:
        predicate = scope_predicate(self.admin, "room")
        fixture_rooms = select(Room).where(Room.room_code.like(f"{self.prefix}_%"))
        rows = self.session.scalars(
            apply_scope(fixture_rooms, self.admin, "room").order_by(Room.room_code)
        ).all()

        self.assertIsNone(predicate)
        self.assertEqual([row.id for row in rows], [self.room_a.id, self.room_b.id])

    def test_site_scoped_staff_sees_only_that_site_for_room_and_rent_confirm(self) -> None:
        room_rows = self.session.scalars(
            apply_scope(select(Room), self.staff, "room").order_by(Room.room_code)
        ).all()
        confirm_rows = self.session.scalars(
            apply_scope(select(RentConfirm), self.staff, "rent_confirm").order_by(RentConfirm.id)
        ).all()

        self.assertEqual([row.id for row in room_rows], [self.room_a.id])
        self.assertNotIn(self.room_b.id, [row.id for row in room_rows])
        self.assertEqual([row.id for row in confirm_rows], [self.confirm_a.id])
        self.assertNotIn(self.confirm_b.id, [row.id for row in confirm_rows])

    def test_allowed_columns_and_mask_row_hide_tenant_contract_sensitive_fields_from_staff(self) -> None:
        allowed = allowed_columns("staff", "tenant_contract")
        row = {"room_id": self.room_a.id, "contact_name": "Alice", "contact_phone": "0912", "rent": 1000}

        self.assertIn("room_id", allowed)
        self.assertIn("contact_name", allowed)
        self.assertNotIn("contact_phone", allowed)
        self.assertNotIn("rent", allowed)
        self.assertEqual(mask_row(row, allowed), {"room_id": self.room_a.id, "contact_name": "Alice"})

    def test_require_roles_blocks_wrong_role_with_403(self) -> None:
        test_app = FastAPI()

        def override_get_db():
            yield self.session

        test_app.dependency_overrides[get_db] = override_get_db

        @test_app.get("/manager-only")
        def manager_only(_: AppUser = Depends(require_roles("manager"))) -> dict[str, bool]:
            return {"ok": True}

        response = TestClient(test_app).get("/manager-only", headers=self.auth_headers(self.staff))

        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
