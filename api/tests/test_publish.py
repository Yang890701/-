import os
import unittest
from datetime import date
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
from app.db.models import (
    AppUser,
    AuditLog,
    BillingRun,
    BillingRunDetail,
    EnumFeeItem,
    ExceptionCharge,
    RentConfirm,
    Room,
    RoomFixedFee,
    Site,
    TenantContract,
)
from app.db.session import get_db
from app.main import app
from app.meta.seed import seed_metadata


class BillingPublishApiTest(unittest.TestCase):
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
        self.prefix = f"publish_{uuid4().hex}"
        seed_metadata(self.session, actor="test")
        self.admin = self.create_user("admin")
        self.staff = self.create_user("staff")

        self.site = Site(site_code=f"{self.prefix}_site", name="Publish Site")
        self.session.add(self.site)
        self.session.flush()
        self.room = Room(site_id=self.site.id, room_code=f"{self.prefix}_101", room_name="Publish Room")
        self.session.add(self.room)
        self.session.flush()
        self._add_publish_components()
        self.session.commit()

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.session.close()
        if self.transaction.is_active:
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

    def auth_headers(self, user: AppUser | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(user or self.admin)}"}

    def _add_publish_components(self) -> None:
        old_contract = TenantContract(
            room_id=self.room.id,
            lease_start_date=date(2025, 1, 1),
            lease_end_date=date(2026, 5, 31),
            rent=10000,
        )
        active_contract = TenantContract(
            room_id=self.room.id,
            lease_start_date=date(2026, 6, 1),
            lease_end_date=None,
            rent=12000,
        )
        fee_item_a = EnumFeeItem(code=f"{self.prefix}_fee_a", label="Fee A")
        fee_item_b = EnumFeeItem(code=f"{self.prefix}_fee_b", label="Fee B")
        self.session.add_all([old_contract, active_contract, fee_item_a, fee_item_b])
        self.session.flush()
        self.session.add_all(
            [
                RoomFixedFee(room_id=self.room.id, fee_item_id=fee_item_a.id, amount=300),
                RoomFixedFee(room_id=self.room.id, fee_item_id=fee_item_b.id, amount=200),
                ExceptionCharge(room_id=self.room.id, billing_ym="202606", charge_type="adjustment", amount=75),
                ExceptionCharge(room_id=self.room.id, billing_ym="202606", charge_type="repair", amount=25),
            ]
        )

    def create_run(self, status: str = "calculated", subtotal: int = 321) -> BillingRun:
        run = BillingRun(
            billing_ym="202606",
            version=1,
            scope={"room_ids": [self.room.id]},
            status=status,
            idempotency_key=f"{self.prefix}_run_{uuid4().hex}",
            input_snapshot={
                "summary": {
                    "total_rooms": 1,
                    "calculated": 1,
                    "skipped": 0,
                    "total_amount": subtotal,
                    "by_site": [{"site_id": self.site.id, "total_amount": subtotal, "calculated": 1, "skipped": 0}],
                }
            },
            created_by=self.admin.id,
        )
        self.session.add(run)
        self.session.flush()
        self.session.add(
            BillingRunDetail(
                run_id=run.id,
                room_id=self.room.id,
                subtotal=subtotal,
                status="calculated",
            )
        )
        self.session.commit()
        self.session.refresh(run)
        return run

    def rent_confirm_rows(self, run: BillingRun) -> list[RentConfirm]:
        return list(
            self.session.scalars(
                select(RentConfirm)
                .where(
                    RentConfirm.room_id == self.room.id,
                    RentConfirm.billing_ym == run.billing_ym,
                    RentConfirm.run_version == run.version,
                    RentConfirm.deleted_at.is_(None),
                )
                .order_by(RentConfirm.id.asc())
            )
        )

    def approve_and_publish(self) -> BillingRun:
        run = self.create_run()
        approve = self.client.post(f"/api/billing/runs/{run.id}/approve", headers=self.auth_headers())
        publish = self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers())
        self.assertEqual(approve.status_code, 200)
        self.assertEqual(publish.status_code, 200)
        self.session.refresh(run)
        return run

    def test_calculated_approve_publish_creates_rent_confirm_with_component_sums(self) -> None:
        run = self.create_run()

        approve = self.client.post(f"/api/billing/runs/{run.id}/approve", headers=self.auth_headers())
        publish = self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers())

        self.assertEqual(approve.status_code, 200)
        self.assertEqual(approve.json()["status"], "approved")
        self.assertEqual(publish.status_code, 200)
        self.assertEqual(publish.json()["status"], "published")
        rows = self.rent_confirm_rows(run)
        self.assertEqual(len(rows), 1)
        confirm = rows[0]
        self.assertEqual(confirm.charge_type, "月結")
        self.assertEqual(confirm.status, "已確認")
        self.assertEqual(confirm.rent_amount, 12000)
        self.assertEqual(confirm.electricity_amount, 321)
        self.assertEqual(confirm.fixed_fee_amount, 500)
        self.assertEqual(confirm.exception_amount, 100)
        self.assertEqual(confirm.total_amount, 12921)
        self.assertEqual(confirm.amounts["rent"]["amount"], 12000)
        self.assertEqual(confirm.amounts["electricity"]["amount"], 321)

    def test_duplicate_publish_on_published_run_returns_409(self) -> None:
        run = self.approve_and_publish()

        duplicate = self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers())

        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("already published", duplicate.json()["detail"])
        self.assertEqual(len(self.rent_confirm_rows(run)), 1)

    def test_publish_on_non_approved_run_returns_409(self) -> None:
        run = self.create_run(status="calculated")

        response = self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers())

        self.assertEqual(response.status_code, 409)
        self.assertIn("approved", response.json()["detail"])
        self.assertEqual(len(self.rent_confirm_rows(run)), 0)

    def test_reverse_creates_negated_rows_and_keeps_originals(self) -> None:
        run = self.approve_and_publish()

        response = self.client.post(f"/api/billing/runs/{run.id}/reverse", headers=self.auth_headers())

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "reversed")
        self.session.refresh(run)
        self.assertEqual(run.status, "reversed")
        rows = self.rent_confirm_rows(run)
        self.assertEqual(len(rows), 2)
        original, reversal = rows
        self.assertEqual(original.charge_type, "月結")
        self.assertEqual(reversal.charge_type, "沖銷")
        self.assertEqual(reversal.status, "作廢")
        self.assertEqual(reversal.rent_amount, -original.rent_amount)
        self.assertEqual(reversal.electricity_amount, -original.electricity_amount)
        self.assertEqual(reversal.fixed_fee_amount, -original.fixed_fee_amount)
        self.assertEqual(reversal.exception_amount, -original.exception_amount)
        self.assertEqual(reversal.total_amount, -original.total_amount)

    def test_staff_publish_returns_403(self) -> None:
        run = self.create_run(status="approved")

        response = self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers(self.staff))

        self.assertEqual(response.status_code, 403)
        self.assertEqual(len(self.rent_confirm_rows(run)), 0)

    def test_each_transition_writes_audit_log(self) -> None:
        run = self.create_run()
        before = self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "billing_run")
        )

        self.client.post(f"/api/billing/runs/{run.id}/approve", headers=self.auth_headers())
        self.client.post(f"/api/billing/runs/{run.id}/publish", headers=self.auth_headers())
        self.client.post(f"/api/billing/runs/{run.id}/reverse", headers=self.auth_headers())

        after = self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "billing_run")
        )
        actions = self.session.scalars(
            select(AuditLog.action)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == "billing_run")
            .order_by(AuditLog.id.desc())
            .limit(3)
        ).all()
        self.assertEqual(after, before + 3)
        self.assertEqual(
            list(reversed(actions)),
            ["billing_run_approve", "billing_run_publish", "billing_run_reverse"],
        )


if __name__ == "__main__":
    unittest.main()
