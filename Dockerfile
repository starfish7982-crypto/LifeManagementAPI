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

# Run as a non-root user: if the process is compromised it cannot write outside its own data dir.
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /srv/data \
    && chown -R appuser:appuser /srv
USER appuser

ENV DATABASE_URL=sqlite:////srv/data/life.db
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import httpx,sys; sys.exit(0 if httpx.get('http://127.0.0.1:8000/health').status_code==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
