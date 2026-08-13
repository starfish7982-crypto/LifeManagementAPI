#!/bin/sh
# Apply migrations, then hand the process over to the server.
#
# Render's preDeployCommand — the right place for this — is a paid-plan feature, so the
# work moves into container start. The reason preDeploy is normally better is that every
# replica runs this script, and N replicas booting together would race to apply the same
# revision. That is not a risk on the free plan, which runs exactly one instance; it
# becomes one the moment this service scales, and the fix at that point is to move the
# line back into preDeployCommand rather than to add locking here.
#
# `set -e` is what makes a failed migration a failed deploy. Without it the server would
# start against a schema that does not match the code, and the first request would be
# the thing that discovered it.
set -e

echo "Running database migrations..."
alembic upgrade head

# exec, not a plain call: uvicorn replaces this shell as PID 1 and so receives the
# SIGTERM Render sends on shutdown. Left as a child, it would never be asked to stop
# cleanly and would be killed after the grace period instead.
exec uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}"
