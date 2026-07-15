import os
import unittest
from uuid import uuid4

from sqlalchemy import create_engine, delete, select, update
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("JWT_SIGNING_KEYS", '{"dev-test-kid":"dev-test-secret-with-at-least-32-bytes"}')
os.environ.setdefault("JWT_ACTIVE_KID", "dev-test-kid")
os.environ.setdefault("ACCESS_TOKEN_TTL_SECONDS", "1200")
os.environ.setdefault("REFRESH_TOKEN_TTL_SECONDS", "1209600")
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")

from fastapi.testclient import TestClient

from app.auth.passwords import hash_password
from app.auth.tokens import create_access_token
from app.config import settings
from app.db.models import AppUser, AuditLog, RefreshSession
from app.db.session import get_db
from app.main import app


class AuthApiTest(unittest.TestCase):
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
        self.username = f"auth_{uuid4().hex}"
        self.password = "correct-password"
        self.session = self.SessionLocal()

        def override_get_db():
            yield self.session

        app.dependency_overrides[get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self) -> None:
        app.dependency_overrides.clear()
        self.session.rollback()
        self.session.execute(
            delete(RefreshSession).where(
                RefreshSession.user_id.in_(select(AppUser.id).where(AppUser.username == self.username))
            )
        )
        self.session.execute(
            delete(AuditLog).where(
                AuditLog.actor.in_(select(AppUser.id).where(AppUser.username == self.username))
            )
        )
        self.session.execute(delete(AppUser).where(AppUser.username == self.username))
        self.session.commit()
        self.session.close()

    def create_user(self, *, password: str | None = None, token_version: int = 0) -> AppUser:
        user = AppUser(
            username=self.username,
            password_hash=hash_password(password or self.password),
            role="admin",
            token_version=token_version,
        )
        self.session.add(user)
        self.session.commit()
        self.session.refresh(user)
        return user

    def login(self, password: str | None = None):
        return self.client.post(
            "/api/auth/login",
            json={"username": self.username, "password": password or self.password},
        )

    def test_login_success_returns_access_token_user_and_refresh_cookie(self) -> None:
        self.create_user()

        response = self.login()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["token_type"], "bearer")
        self.assertTrue(body["access_token"])
        self.assertEqual(body["user"]["username"], self.username)
        self.assertEqual(body["user"]["role"], "admin")
        self.assertIn("refresh_token", response.cookies)
        self.assertIsNotNone(
            self.session.scalar(select(RefreshSession).where(RefreshSession.user_id == body["user"]["id"]))
        )

    def test_wrong_password_increments_failed_attempts(self) -> None:
        user = self.create_user()

        response = self.login("wrong-password")

        self.assertEqual(response.status_code, 401)
        self.session.refresh(user)
        self.assertEqual(user.failed_login_attempts, 1)

    def test_lockout_after_threshold_blocks_without_password_check(self) -> None:
        old_threshold = settings.lockout_threshold
        old_window = settings.lockout_window_seconds
        settings.lockout_threshold = 2
        settings.lockout_window_seconds = 60
        try:
            user = self.create_user()

            self.assertEqual(self.login("wrong-1").status_code, 401)
            second = self.login("wrong-2")
            self.assertEqual(second.status_code, 423)
            locked = self.login(self.password)

            self.assertIn(locked.status_code, {423, 429})
            self.session.refresh(user)
            self.assertEqual(user.failed_login_attempts, 2)
            self.assertIsNotNone(user.locked_until)
        finally:
            settings.lockout_threshold = old_threshold
            settings.lockout_window_seconds = old_window

    def test_me_accepts_valid_access_and_rejects_invalid_expired_or_tampered_tokens(self) -> None:
        user = self.create_user()
        login = self.login()
        access = login.json()["access_token"]

        valid = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})
        invalid = self.client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
        expired_token = create_access_token(user, ttl_seconds=-1)
        expired = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {expired_token}"})
        tampered_token = access[:-1] + ("a" if access[-1] != "a" else "b")
        tampered = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {tampered_token}"})

        self.assertEqual(valid.status_code, 200)
        self.assertEqual(valid.json()["username"], self.username)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(expired.status_code, 401)
        self.assertEqual(tampered.status_code, 401)

    def test_refresh_issues_new_access_and_rotates_refresh_token(self) -> None:
        self.create_user()
        login = self.login()
        old_refresh = login.cookies["refresh_token"]

        refreshed = self.client.post("/api/auth/refresh")
        new_refresh = refreshed.cookies["refresh_token"]

        self.assertEqual(refreshed.status_code, 200)
        self.assertTrue(refreshed.json()["access_token"])
        self.assertNotEqual(new_refresh, old_refresh)
        self.client.cookies.set("refresh_token", old_refresh)
        reused = self.client.post("/api/auth/refresh")
        self.assertEqual(reused.status_code, 401)

    def test_logout_revokes_current_refresh_token(self) -> None:
        self.create_user()
        self.login()

        logout = self.client.post("/api/auth/logout")
        refreshed = self.client.post("/api/auth/refresh")

        self.assertEqual(logout.status_code, 204)
        self.assertEqual(refreshed.status_code, 401)

    def test_bumping_token_version_invalidates_old_access(self) -> None:
        user = self.create_user(token_version=0)
        access = self.login().json()["access_token"]
        self.session.execute(update(AppUser).where(AppUser.id == user.id).values(token_version=1))
        self.session.commit()

        response = self.client.get("/api/auth/me", headers={"Authorization": f"Bearer {access}"})

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
