"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import Base, engine
from app.routers import assets, auth, reminders, today, todos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

DEV_JWT_SECRET = "dev-secret-change-me"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    # Fail loudly at boot rather than quietly signing tokens anyone can forge. The
    # check keys off the database rather than an explicit ENV flag because that is the
    # signal that cannot be forgotten: if this process is talking to a real database,
    # it is not a scratch run, whatever the environment variables claim.
    if not settings.is_local_sqlite and settings.jwt_secret == DEV_JWT_SECRET:
        raise RuntimeError(
            "JWT_SECRET is still the development default. Set it to a random secret "
            "(e.g. `openssl rand -hex 32`) before running against a real database."
        )

    # Bootstrap the schema for local SQLite only, so a fresh clone runs with no extra
    # step. Deliberately NOT done against a real database: create_all builds tables
    # without writing an alembic_version row, so Alembic later finds a populated schema
    # it has no history for and tries to create everything from scratch. That failure
    # ("relation already exists", on every deploy, unrecoverable without dropping the
    # tables by hand) is exactly what this guard prevents. Managed databases get their
    # schema from `alembic upgrade head` in docker-entrypoint.sh — one owner, not two.
    if settings.is_local_sqlite:
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Life Management API",
    version="0.1.0",
    description=(
        "REST API for personal asset snapshots, recurring reminders, and daily todos, "
        "integrating Google Calendar and Telegram."
    ),
    lifespan=lifespan,
)

# Explicit origins, never "*". The browser sends the Authorization header on these
# requests, so a wildcard would let any page on the internet drive this API with a
# token it tricked the user's browser into attaching.
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(reminders.router)
app.include_router(todos.router)
app.include_router(today.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Unauthenticated liveness probe, used by the Docker and Render health checks."""
    return {"status": "ok"}
