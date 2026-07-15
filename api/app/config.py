import json

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str
    jwt_signing_keys: str | None = None
    jwt_active_kid: str | None = None
    access_token_ttl_seconds: int = 20 * 60
    refresh_token_ttl_seconds: int = 14 * 24 * 60 * 60
    lockout_threshold: int = 5
    lockout_window_seconds: int = 15 * 60
    auth_cookie_secure: bool = False
    auth_refresh_cookie_name: str = "refresh_token"
    object_store_endpoint: str | None = None
    object_store_key: str | None = None
    object_store_secret: str | None = None
    object_store_bucket: str | None = None
    cors_allowlist: str = "http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def jwt_key_map(self) -> dict[str, str]:
        if not self.jwt_signing_keys:
            raise RuntimeError("JWT_SIGNING_KEYS must be set")
        parsed = json.loads(self.jwt_signing_keys)
        if not isinstance(parsed, dict) or not parsed:
            raise RuntimeError("JWT_SIGNING_KEYS must be a non-empty JSON object")
        keys = {str(kid): str(secret) for kid, secret in parsed.items()}
        if any(not secret for secret in keys.values()):
            raise RuntimeError("JWT_SIGNING_KEYS contains an empty secret")
        return keys

    def active_jwt_key(self) -> tuple[str, str]:
        keys = self.jwt_key_map()
        kid = self.jwt_active_kid or next(iter(keys))
        if kid not in keys:
            raise RuntimeError("JWT_ACTIVE_KID is not present in JWT_SIGNING_KEYS")
        return kid, keys[kid]


settings = Settings()
