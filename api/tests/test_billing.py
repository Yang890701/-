import os
import unittest
from decimal import Decimal
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
    AvgPrice,
    BillingRun,
    BillingRunDetail,
    GoldenCase,
    Meter,
    MeterReading,
    ReadingException,
    Room,
    RoomMeterAssignment,
    Site,
)
from app.db.session import get_db
from app.main import app
from app.meta.seed import seed_metadata


class BillingApiTest(unittest.TestCase):
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
        self.prefix = f"billing_{uuid4().hex}"
        seed_metadata(self.session, actor="test")
        self.admin = self.create_user("admin")
        self.site = Site(site_code=f"{self.prefix}_site", name="Billing Site")
        self.session.add(self.site)
        self.session.flush()

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

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(self.admin)}"}

    def create_normal_room(
        self,
        *,
        room_code: str = "101",
        effective_from_ym: str = "202605",
        prior_ym: str | None = "202605",
        prior_reading: int | None = 120,
        current_ym: str = "202606",
        current_reading: int = 150,
        initial_reading: int = 100,
        price: Decimal = Decimal("4.2000"),
    ) -> Room:
        meter = Meter(electricity_code=f"{self.prefix}_{room_code}_meter", name=f"Meter {room_code}")
        room = Room(
            site_id=self.site.id,
            room_code=f"{self.prefix}_{room_code}",
            room_name=f"Room {room_code}",
            billing_mode="normal",
        )
        self.session.add_all([meter, room])
        self.session.flush()
        assignment = RoomMeterAssignment(
            room_id=room.id,
            meter_id=meter.id,
            effective_from_ym=effective_from_ym,
            initial_reading=initial_reading,
            meter_category="main",
        )
        self.session.add(assignment)
        self.session.flush()
        if prior_ym is not None and prior_reading is not None:
            self.session.add(
                MeterReading(
                    assignment_id=assignment.id,
                    billing_ym=prior_ym,
                    reading_kind="routine",
                    reading=prior_reading,
                )
            )
        self.session.add_all(
            [
                MeterReading(
                    assignment_id=assignment.id,
                    billing_ym=current_ym,
                    reading_kind="routine",
                    reading=current_reading,
                ),
                AvgPrice(meter_id=meter.id, billing_ym=current_ym, price=price),
            ]
        )
        self.session.commit()
        return room

    def run_billing(self, *, idempotency_key: str | None = None):
        payload = {"billing_ym": "202606", "scope": {"site_id": self.site.id}}
        if idempotency_key is not None:
            payload["idempotency_key"] = idempotency_key
        return self.client.post("/api/billing/runs", json=payload, headers=self.auth_headers())

    def test_normal_mode_run_creates_calculated_detail_with_hand_value(self) -> None:
        room = self.create_normal_room()

        response = self.run_billing()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "calculated")
        self.assertEqual(body["summary"]["calculated"], 1)
        self.assertEqual(body["summary"]["total_amount"], 126)
        run = self.session.get(BillingRun, body["run_id"])
        detail = self.session.scalar(
            select(BillingRunDetail).where(BillingRunDetail.run_id == run.id, BillingRunDetail.room_id == room.id)
        )
        self.assertEqual(run.status, "calculated")
        self.assertEqual(detail.subtotal, 126)
        self.assertEqual(detail.status, "calculated")

    def test_missing_prior_reading_skips_room_and_records_exception(self) -> None:
        room = self.create_normal_room(
            room_code="missing_prior",
            effective_from_ym="202604",
            prior_ym=None,
            prior_reading=None,
            current_ym="202606",
            current_reading=150,
        )

        response = self.run_billing()

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["status"], "calculated")
        self.assertEqual(body["summary"]["calculated"], 0)
        self.assertEqual(body["summary"]["skipped"], 1)
        detail = self.session.scalar(
            select(BillingRunDetail).where(
                BillingRunDetail.run_id == body["run_id"],
                BillingRunDetail.room_id == room.id,
            )
        )
        exception = self.session.scalar(
            select(ReadingException).where(ReadingException.billing_ym == "202606")
        )
        self.assertIsNone(detail.subtotal)
        self.assertEqual(detail.status, "skipped")
        self.assertIsNotNone(exception)
        self.assertIn("prior", exception.reason.lower())

    def test_same_idempotency_key_returns_same_existing_run(self) -> None:
        self.create_normal_room()

        first = self.run_billing(idempotency_key=f"{self.prefix}_same")
        second = self.run_billing(idempotency_key=f"{self.prefix}_same")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(second.json()["run_id"], first.json()["run_id"])
        self.assertEqual(
            self.session.scalar(select(func.count()).select_from(BillingRun).where(BillingRun.billing_ym == "202606")),
            1,
        )

    def test_second_run_for_same_period_and_scope_returns_409(self) -> None:
        self.create_normal_room()

        first = self.run_billing()
        duplicate = self.run_billing()

        self.assertEqual(first.status_code, 201)
        self.assertEqual(duplicate.status_code, 409)
        self.assertIn("billing run already exists", duplicate.json()["detail"].lower())


class BillingGoldenCaseTest(unittest.TestCase):
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

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def test_seeded_golden_cases_compute_expected_electricity(self) -> None:
        from app.meta.billing_golden import seed_golden_cases
        from app.services.billing import compute_golden_case

        counts = seed_golden_cases(self.session)
        cases = self.session.scalars(
            select(GoldenCase)
            .where(GoldenCase.case_code.like("billing_%"))
            .order_by(GoldenCase.case_code.asc())
        ).all()
        modes = {case.input_data["mode"] for case in cases}

        self.assertGreaterEqual(counts["total"], 15)
        self.assertEqual(
            modes,
            {"jingping_merge", "normal", "special_price", "total_bill_split", "total_sub"},
        )

        for case in cases:
            with self.subTest(case_code=case.case_code):
                computed = compute_golden_case(case.input_data)
                self.assertEqual(computed["electricity_amount"], case.expected_output["electricity_amount"])


if __name__ == "__main__":
    unittest.main()
