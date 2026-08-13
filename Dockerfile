FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# pyproject declares packages = ["app", ...], so the package must be present before
# `pip install .` runs. Copying both first costs some layer caching (a source-only edit
# reinstalls dependencies) and buys a build that actually works. For a project this
# size that is the right trade; a larger one would split dependencies into a lock file
# installed in its own layer.
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir .

# The entrypoint runs `alembic upgrade head` before starting the server, so the config
# and the revision history have to be in the image.
COPY alembic.ini ./
COPY alembic ./alembic
COPY docker-entrypoint.sh ./
# chmod in the image rather than relying on the checked-in file mode: a clone on Windows,
# or an archive export, can lose the execute bit and the container would fail to start.
RUN chmod +x docker-entrypoint.sh

# Run as a non-root user: if the process is compromised it cannot write outside its own data dir.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /srv/data \
    && chown -R appuser:appuser /srv
USER appuser

# Fallback only. Any real deployment sets DATABASE_URL to a managed Postgres URL —
# a container filesystem is ephemeral, so SQLite here survives only until the next restart.
ENV DATABASE_URL=sqlite:////srv/data/life.db

# Hosts like Render inject the port to bind on via $PORT. Defaulting keeps `docker run`
# working locally without extra flags.
ENV PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import httpx,os,sys; sys.exit(0 if httpx.get(f\"http://127.0.0.1:{os.environ.get('PORT','8000')}/health\").status_code==200 else 1)"

# The entrypoint migrates, then execs uvicorn. A failed migration aborts the start,
# which is what stops the server from ever serving against a mismatched schema.
CMD ["./docker-entrypoint.sh"]
