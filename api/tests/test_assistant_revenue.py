"""execute_revenue 金額語意守門測試(review 3fe719b 揪出的 high bug 回歸)。

三個不變量:
1. 沖銷→重開:舊版與其沖銷一併淘汰,只算新版(曾少算整版金額)。
2. 沖銷未重開:合計歸零(月費用被作廢)。
3. 無帳月(billing_ym NULL)列不入任何統計;重算多版只取最新版。
"""
import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")

from app.assistant.tools import execute_aggregate, execute_revenue
from app.auth.passwords import hash_password
from app.db.models import AppUser, RentConfirm, Room, Site
from app.meta.seed import seed_metadata
from app.services.billing import (
    MONTHLY_RENT_CONFIRM_CHARGE_TYPE,
    PUBLISHED_RENT_CONFIRM_STATUS,
    REVERSAL_RENT_CONFIRM_CHARGE_TYPE,
    REVERSAL_RENT_CONFIRM_STATUS,
)

YM = "209912"  # 真實資料不存在的月份,隔離本測試


class AssistantRevenueTest(unittest.TestCase):
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
        self.prefix = f"rev_{uuid4().hex[:10]}"
        seed_metadata(self.session, actor="test")
        self.admin = AppUser(
            username=f"{self.prefix}_admin",
            password_hash=hash_password("password"),
            role="admin",
            token_version=0,
        )
        self.session.add(self.admin)
        self.site = Site(site_code=f"{self.prefix}_site", name=f"{self.prefix}_社區")
        self.session.add(self.site)
        self.session.flush()
        self.rooms = {}
        for code in ("A", "B", "C"):
            room = Room(site_id=self.site.id, room_code=f"{self.prefix}_{code}", room_name=code)
            self.session.add(room)
            self.rooms[code] = room
        self.session.flush()

        def rc(room: Room, ym: str | None, charge_type: str, rv: int, total: int, status: str) -> None:
            self.session.add(
                RentConfirm(
                    room_id=room.id,
                    billing_ym=ym,
                    charge_type=charge_type,
                    run_version=rv,
                    status=status,
                    rent_amount=total,
                    total_amount=total,
                )
            )

        a, b, c = self.rooms["A"], self.rooms["B"], self.rooms["C"]
        # A:v1 開帳 → 沖銷 v1 → 重開 v2(正確合計 = 12000)
        rc(a, YM, MONTHLY_RENT_CONFIRM_CHARGE_TYPE, 1, 10000, PUBLISHED_RENT_CONFIRM_STATUS)
        rc(a, YM, REVERSAL_RENT_CONFIRM_CHARGE_TYPE, 1, -10000, REVERSAL_RENT_CONFIRM_STATUS)
        rc(a, YM, MONTHLY_RENT_CONFIRM_CHARGE_TYPE, 2, 12000, PUBLISHED_RENT_CONFIRM_STATUS)
        # A:無帳月殘留(不得混入任何統計)
        rc(a, None, "monthly_receivable", 1, 5000, "imported")
        # B:沖銷後未重開(正確合計 = 0)
        rc(b, YM, MONTHLY_RENT_CONFIRM_CHARGE_TYPE, 1, 8000, PUBLISHED_RENT_CONFIRM_STATUS)
        rc(b, YM, REVERSAL_RENT_CONFIRM_CHARGE_TYPE, 1, -8000, REVERSAL_RENT_CONFIRM_STATUS)
        # C:匯入資料重算兩版(只算最新版 3000)
        rc(c, YM, "monthly_receivable", 1, 999999, "imported")
        rc(c, YM, "monthly_receivable", 2, 3000, "imported")
        self.session.flush()

    def tearDown(self) -> None:
        self.session.close()
        if self.transaction.is_active:
            self.transaction.rollback()
        self.connection.close()

    def test_month_total_reversal_and_null_ym(self) -> None:
        rows = execute_revenue(self.session, self.admin, billing_ym=YM, by="month")
        self.assertEqual(len(rows), 1)
        self.assertEqual(float(rows[0]["value"]), 15000.0)  # 12000 + 0 + 3000;NULL-ym 5000 不入

    def test_by_room_breakdown_and_order(self) -> None:
        rows = execute_revenue(self.session, self.admin, billing_ym=YM, by="room")
        got = {r["group"]: float(r["value"]) for r in rows}
        self.assertEqual(got[f"{self.prefix}_A"], 12000.0)  # 沖銷+重開 → 只算新版
        self.assertEqual(got[f"{self.prefix}_B"], 0.0)  # 沖銷未重開 → 歸零
        self.assertEqual(got[f"{self.prefix}_C"], 3000.0)  # 重算 → 最新版
        self.assertEqual(set(got), {f"{self.prefix}_{c}" for c in "ABC"})
        self.assertEqual(rows[0]["group"], f"{self.prefix}_A")  # 預設 desc
        asc = execute_revenue(self.session, self.admin, billing_ym=YM, by="room", order="asc")
        self.assertEqual(asc[0]["group"], f"{self.prefix}_B")

    def test_by_site_total(self) -> None:
        rows = execute_revenue(self.session, self.admin, billing_ym=YM, by="site")
        got = {r["group"]: float(r["value"]) for r in rows}
        self.assertEqual(got[f"{self.prefix}_社區"], 15000.0)

    def test_aggregate_blocks_rent_confirm_money(self) -> None:
        with self.assertRaises(ValueError):
            execute_aggregate(
                self.session, self.admin, "rent_confirm",
                group_by="billing_ym", fn="sum", measure_col="total_amount",
            )
