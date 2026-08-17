# ---------------------------------------------------------------- frontend build
#
# The UI is TypeScript and JSX, which no browser runs directly, so it has to be
# compiled. Doing that in its own stage means Node and the 196 packages it pulls in
# stay out of the final image entirely — only the handful of built files are copied
# across. The runtime image has no npm, no node_modules, and nothing to audit.
FROM node:22-slim AS web

WORKDIR /web

# Manifests first, on their own layer. Dependencies change far less often than source,
# so an edit to a component reuses the cached npm install instead of repeating it.
COPY web/package.json web/package-lock.json* ./
# `npm ci` when there is a lockfile: it installs exactly what the lockfile pins and
# fails if the two disagree, which is the property that makes a build reproducible.
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi

COPY web/ ./
# `npm run build` runs tsc --noEmit first, so a type error fails the image build rather
# than shipping. The check belongs here as well as in CI: this is the last gate before
# something reaches production.
RUN npm run build


# ------------------------------------------------------------------------ runtime
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# Tesseract reads uploaded receipt images. English is enough for figures and common
# receipt labels; Traditional Chinese allows labels such as 合計 / 總計 to be detected.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-chi-tra \
    && rm -rf /var/lib/apt/lists/*

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

# Just the compiled output from the build stage. app/main.py mounts this at /app.
COPY --from=web /web/dist ./web/dist

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
