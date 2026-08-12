"""Database engine, session factory, and the FastAPI session dependency."""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def normalize_url(url: str) -> str:
    """Rewrite the URL forms hosted Postgres providers hand out into ones SQLAlchemy accepts.

    Neon, Supabase, and Render all print connection strings starting with `postgres://`,
    which SQLAlchemy dropped support for in 2.0. Bare `postgresql://` still resolves to
    the psycopg2 driver, which this project does not install — psycopg 3 is the
    maintained one. Normalising here means the deployment can paste the provider's
    string into DATABASE_URL verbatim and it just works.
    """
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def _engine_kwargs(url: str) -> dict:
    # SQLite refuses connections shared across threads by default. FastAPI runs sync
    # endpoints in a threadpool, so the flag is required. It is NOT needed (and not
    # valid) for Postgres, hence the conditional.
    if url.startswith("sqlite"):
        return {"connect_args": {"check_same_thread": False}}
    # Serverless Postgres (Neon, Supabase) drops idle connections, and free-tier hosts
    # idle the whole app out. Without pre-ping the first request after a wake-up fails
    # on a stale pooled connection; recycling caps how stale a connection can get.
    return {"pool_pre_ping": True, "pool_recycle": 300}


settings = get_settings()
DATABASE_URL = normalize_url(settings.database_url)
engine = create_engine(DATABASE_URL, **_engine_kwargs(DATABASE_URL))
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
