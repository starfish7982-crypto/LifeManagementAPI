"""Application entrypoint."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import Base, engine
from app.routers import assets, reminders, today, todos

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # create_all is adequate for a single-writer SQLite service. A multi-instance
    # deployment would need Alembic migrations instead, because create_all cannot
    # alter an existing table.
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assets.router)
app.include_router(reminders.router)
app.include_router(todos.router)
app.include_router(today.router)


@app.get("/health", tags=["meta"])
def health() -> dict[str, str]:
    """Unauthenticated liveness probe, used by Docker and Fly.io health checks."""
    return {"status": "ok"}
