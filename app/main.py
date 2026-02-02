from fastapi import FastAPI
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import Base, engine, SessionLocal
from app.routers.auth import router as auth_router
from app.routers.tow_jobs import router as tow_jobs_router
from app.routers.users import router as users_router
from app.routers.admin import router as admin_router
from app.services.seed import seed_users
from app.web.router import router as web_router

# Import models so SQLAlchemy registers them before create_all()
import app.models.user  # noqa: F401
import app.models.tow_job  # noqa: F401
import app.models.photo  # noqa: F401
import app.models.event  # noqa: F401

app = FastAPI(title=settings.APP_NAME, version="0.1.0")

Base.metadata.create_all(bind=engine)

with SessionLocal() as db:  # type: Session
    seed_users(db)

app.include_router(auth_router)
app.include_router(tow_jobs_router)
app.include_router(users_router)
app.include_router(admin_router)
app.include_router(web_router)


@app.get("/")
def root():
    return {"name": settings.APP_NAME, "docs": "/docs", "health": "/health"}


@app.get("/health")
def health():
    return {"ok": True}
