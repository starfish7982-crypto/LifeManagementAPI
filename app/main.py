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
from app.routers import assets, auth, grocery, ideas, lists, reminders, today, todos, travel

# Aliased on its own line: `settings` is already the name of the application config
# object throughout this file, and importing the router under that name would shadow it.
from app.routers import settings as settings_router

# app/main.py -> app/ -> the project root, which is /srv in the container.
#
# The UI is a Vite build, so what gets served is `web/dist`, not the source in `web/src`.
# A source checkout that has never run `npm run build` has no dist directory; the mount
# below is guarded so that degrades to "API only" rather than refusing to start — the
# test suite and the import script have no use for the UI.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
FRONTEND_DIR = PROJECT_ROOT / "web" / "dist"

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
app.include_router(grocery.router)
app.include_router(ideas.router)
app.include_router(lists.router)
app.include_router(reminders.router)
app.include_router(settings_router.router)
app.include_router(todos.router)
app.include_router(today.router)
app.include_router(travel.router)


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


class HashedAssetStaticFiles(StaticFiles):
    """Cache built assets forever, and never cache the file that names them.

    Vite writes a content hash into every filename it emits — `index-D4ZkPgJ.js`. A
    file with that name can never change: change the contents and you get a different
    name. So it is safe to tell the browser to keep it for a year and not ask again,
    which is what `immutable` means.

    `index.html` is the opposite. Its whole job is to say which hashed files the
    current version uses, so a cached copy is how a browser ends up running last
    week's JavaScript. It gets `no-cache` — which does not mean "do not store" but
    "store it and ask before reusing", so a revalidation still returns 304 with an
    empty body when nothing changed.

    This pairing is what makes the deploy safe: one small conditional request finds the
    new asset names, and everything they point at is either already cached or genuinely
    new. Before there was a build step, no filename carried a hash and the only
    available answer was `no-cache` on everything.
    """

    IMMUTABLE = "public, max-age=31536000, immutable"

    def file_response(self, full_path, stat_result, scope, status_code=200):
        response = super().file_response(full_path, stat_result, scope, status_code)
        path = scope.get("path", "")
        response.headers["Cache-Control"] = (
            self.IMMUTABLE if "/assets/" in path else "no-cache"
        )
        return response


# Mounted last. A mount claims every path beneath it, so mounting at /app before the
# routers were registered would be harmless here, but mounting the UI at "/" would
# swallow /todos, /docs and the rest. /app keeps the two namespaces from overlapping
# at all, which is a boundary that cannot be got wrong later by adding a route.
#
# The directory is absent in a source checkout only if someone deletes it; guarding the
# mount means a missing frontend degrades to "no UI" instead of refusing to boot the API.
if FRONTEND_DIR.is_dir():
    app.mount("/app", HashedAssetStaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
else:
    logging.warning(
        "%s not found; serving the API only. Run `npm run build` in web/ to build the UI.",
        FRONTEND_DIR,
    )
