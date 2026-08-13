"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.database import Base, engine
from app.routers import assets, auth, lists, reminders, today, todos

# app/main.py -> app/ -> the project root, which is /srv in the container.
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"

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

# The UI is served from this same app, so the browser never makes a cross-origin
# request and none of this is needed for it. CORS stays configured — empty by default —
# for the case it actually covers: another client, on another origin, calling this API.
# Explicit origins, never "*": these requests carry an Authorization header, and a
# wildcard would let any page on the internet drive the API with a token it convinced
# the browser to attach.
if get_settings().cors_origin_list:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_settings().cors_origin_list,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

app.include_router(auth.router)
app.include_router(assets.router)
app.include_router(lists.router)
app.include_router(reminders.router)
app.include_router(todos.router)
app.include_router(today.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Unauthenticated liveness probe, used by the Docker and Render health checks."""
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    """Send the bare domain to the app rather than to a 404.

    The API occupies the root path, so the UI lives under /app. Keeping it that way
    round — rather than the more conventional /api prefix for the endpoints — avoids
    changing every URL that is already deployed, documented, and used by the import
    script, for a cosmetic gain.
    """
    return RedirectResponse(url="/app/")


# Mounted last. A mount claims every path beneath it, so mounting at /app before the
# routers were registered would be harmless here, but mounting the UI at "/" would
# swallow /todos, /docs and the rest. /app keeps the two namespaces from overlapping
# at all, which is a boundary that cannot be got wrong later by adding a route.
#
# The directory is absent in a source checkout only if someone deletes it; guarding the
# mount means a missing frontend degrades to "no UI" instead of refusing to boot the API.
if FRONTEND_DIR.is_dir():
    app.mount("/app", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:  # pragma: no cover - only reachable with a broken checkout
    logging.warning("frontend/ not found at %s; serving the API only", FRONTEND_DIR)
