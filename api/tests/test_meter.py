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
    AuditLog,
    AvgPrice,
    Meter,
    MeterEvent,
    MeterReading,
    ReadingException,
    Room,
    RoomMeterAssignment,
    Site,
)
from app.db.session import get_db
from app.main import app
from app.meta.seed import seed_metadata


class MeterApiTest(unittest.TestCase):
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
        self.prefix = f"meter_{uuid4().hex}"
        seed_metadata(self.session, actor="test")
        self.admin = self.create_user("admin")
        self.site = Site(site_code=f"{self.prefix}_site", name="Meter Site")
        self.meter = Meter(electricity_code=f"{self.prefix}_m1", name="Main meter")
        self.new_meter = Meter(electricity_code=f"{self.prefix}_m2", name="Replacement meter")
        self.session.add_all([self.site, self.meter, self.new_meter])
        self.session.flush()
        self.room = Room(site_id=self.site.id, room_code=f"{self.prefix}_101", room_name="Room 101")
        self.session.add(self.room)
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

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_access_token(self.admin)}"}

    def create_assignment(
        self,
        *,
        room_id: int | None = None,
        meter_id: int | None = None,
        category: str = "電",
        effective_from_ym: str = "202601",
        initial_reading: int | None = 10,
    ):
        return self.client.post(
            "/api/meter-assignments",
            json={
                "room_id": room_id or self.room.id,
                "meter_id": meter_id or self.meter.id,
                "meter_category": category,
                "effective_from_ym": effective_from_ym,
                "initial_reading": initial_reading,
            },
            headers=self.auth_headers(),
        )

    def test_overlapping_assignment_for_same_room_category_returns_409(self) -> None:
        first = self.create_assignment(effective_from_ym="202601")
        overlap = self.create_assignment(effective_from_ym="202602")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(overlap.status_code, 409)
        self.assertIn("overlap", overlap.json()["detail"].lower())

    def test_change_meter_closes_current_creates_adjacent_assignment_and_event(self) -> None:
        assignment = self.create_assignment(effective_from_ym="202601").json()

        response = self.client.post(
            f"/api/meter-assignments/{assignment['id']}/change-meter",
            json={
                "new_meter_id": self.new_meter.id,
                "event_ym": "202602",
                "final_reading": 120,
                "new_initial_reading": 5,
            },
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        old_assignment = self.session.get(RoomMeterAssignment, assignment["id"])
        new_assignment = self.session.get(RoomMeterAssignment, body["new_assignment"]["id"])
        event = self.session.scalar(
            select(MeterEvent).where(MeterEvent.assignment_id == assignment["id"], MeterEvent.event_type == "換表")
        )

        self.assertEqual(old_assignment.effective_to_ym, "202601")
        self.assertEqual(old_assignment.final_reading, 120)
        self.assertEqual(new_assignment.effective_from_ym, "202602")
        self.assertIsNone(new_assignment.effective_to_ym)
        self.assertEqual(new_assignment.meter_id, self.new_meter.id)
        self.assertEqual(new_assignment.initial_reading, 5)
        self.assertIsNotNone(event)
        self.assertEqual(event.event_ym, "202602")
        self.assertEqual(event.old_reading, 120)
        self.assertEqual(event.new_reading, 5)

    def test_routine_reading_without_prior_period_returns_409(self) -> None:
        assignment = self.create_assignment(effective_from_ym="202601").json()

        response = self.client.post(
            "/api/meter-readings",
            json={
                "assignment_id": assignment["id"],
                "billing_ym": "202603",
                "reading_kind": "例行",
                "reading": 80,
            },
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("須先傳前期", response.json()["detail"])

    def test_initial_period_reading_is_allowed_without_prior(self) -> None:
        assignment = self.create_assignment(effective_from_ym="202601").json()
        before = self.audit_count("meter_reading")

        response = self.client.post(
            "/api/meter-readings",
            json={
                "assignment_id": assignment["id"],
                "billing_ym": "202601",
                "reading_kind": "例行",
                "reading": 30,
            },
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["row"]["assignment_id"], assignment["id"])
        self.assertEqual(body["row"]["reading"], 30)
        self.assertEqual(self.audit_count("meter_reading"), before + 1)

    def test_abnormal_reading_creates_exception_instead_of_hard_failure(self) -> None:
        assignment = self.create_assignment(effective_from_ym="202601").json()
        self.session.add(
            MeterReading(
                assignment_id=assignment["id"],
                billing_ym="202601",
                reading_kind="例行",
                reading=100,
            )
        )
        self.session.commit()
        before = self.audit_count("reading_exception")

        response = self.client.post(
            "/api/meter-readings",
            json={
                "assignment_id": assignment["id"],
                "billing_ym": "202602",
                "reading_kind": "例行",
                "reading": 90,
            },
            headers=self.auth_headers(),
        )

        self.assertEqual(response.status_code, 201)
        body = response.json()
        self.assertEqual(body["kind"], "reading_exception")
        self.assertEqual(body["row"]["assignment_id"], assignment["id"])
        self.assertIn("negative", body["row"]["reason"].lower())
        self.assertIsNone(
            self.session.scalar(
                select(MeterReading).where(
                    MeterReading.assignment_id == assignment["id"],
                    MeterReading.billing_ym == "202602",
                )
            )
        )
        self.assertIsNotNone(
            self.session.scalar(
                select(ReadingException).where(
                    ReadingException.assignment_id == assignment["id"],
                    ReadingException.billing_ym == "202602",
                )
            )
        )
        self.assertEqual(self.audit_count("reading_exception"), before + 1)

    def test_avg_price_duplicate_meter_billing_period_returns_409(self) -> None:
        first = self.client.post(
            "/api/avg-prices",
            json={"meter_id": self.meter.id, "billing_ym": "202601", "price": "4.1250"},
            headers=self.auth_headers(),
        )
        duplicate = self.client.post(
            "/api/avg-prices",
            json={"meter_id": self.meter.id, "billing_ym": "202601", "price": "4.1250"},
            headers=self.auth_headers(),
        )

        self.assertEqual(first.status_code, 201)
        self.assertEqual(Decimal(first.json()["price"]), Decimal("4.1250"))
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(
            self.session.scalar(
                select(func.count()).select_from(AvgPrice).where(AvgPrice.meter_id == self.meter.id)
            ),
            1,
        )

    def test_successful_assignment_change_reading_exception_and_price_write_audit_rows(self) -> None:
        before = self.session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.actor == self.admin.id)
        )

        assignment = self.create_assignment(effective_from_ym="202601").json()
        change = self.client.post(
            f"/api/meter-assignments/{assignment['id']}/change-meter",
            json={
                "new_meter_id": self.new_meter.id,
                "event_ym": "202602",
                "final_reading": 120,
                "new_initial_reading": 5,
            },
            headers=self.auth_headers(),
        )
        missing = self.client.post(
            "/api/meter-readings",
            json={
                "assignment_id": change.json()["new_assignment"]["id"],
                "billing_ym": "202602",
                "reading_kind": "例行",
                "reading": None,
            },
            headers=self.auth_headers(),
        )
        price = self.client.post(
            "/api/avg-prices",
            json={"meter_id": self.meter.id, "billing_ym": "202601", "price": "4.1000"},
            headers=self.auth_headers(),
        )

        self.assertEqual(change.status_code, 201)
        self.assertEqual(missing.status_code, 201)
        self.assertEqual(price.status_code, 201)
        after = self.session.scalar(
            select(func.count()).select_from(AuditLog).where(AuditLog.actor == self.admin.id)
        )
        self.assertEqual(after, before + 4)
        actions = set(
            self.session.scalars(
                select(AuditLog.action).where(AuditLog.actor == self.admin.id).order_by(AuditLog.id.desc()).limit(4)
            )
        )
        self.assertEqual(
            actions,
            {
                "meter_assignment_create",
                "meter_assignment_change",
                "reading_exception_create",
                "avg_price_create",
            },
        )

    def audit_count(self, table_code: str) -> int:
        return self.session.scalar(
            select(func.count())
            .select_from(AuditLog)
            .where(AuditLog.actor == self.admin.id, AuditLog.table_code == table_code)
        )


if __name__ == "__main__":
    unittest.main()
