from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.attachments import router as attachments_router
from app.routers.audit import router as audit_router
from app.routers.auth import router as auth_router
from app.routers.data import router as data_router
from app.routers.meta import router as meta_router

app = FastAPI(title="Haoshi API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowlist.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(meta_router)
app.include_router(data_router)
app.include_router(audit_router)
app.include_router(attachments_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
