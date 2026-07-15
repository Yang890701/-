from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

engine = create_engine(
    settings.database_url,
    future=True,
    # 雲端 Postgres（如 Neon）閒置會自動休眠並關閉連線；
    # pre_ping 在借出連線前先探活、失效則重連，recycle 定期汰換。
    pool_pre_ping=True,
    pool_recycle=300,
)
SessionLocal = sessionmaker(
    bind=engine, autoflush=False, autocommit=False, expire_on_commit=False, future=True
)


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
