# Migrations

`create_all()` in `app/main.py` bootstraps a fresh local database so a clone runs with
no extra step. It cannot ALTER an existing table, so every change to an existing schema
goes through Alembic.

```bash
# after editing app/models.py
alembic revision --autogenerate -m "add days_before to reminders"

# read the generated file before running it — see below
alembic upgrade head

alembic downgrade -1        # undo the last one
alembic current             # what the database thinks it is at
alembic history --verbose   # every revision
```

`DATABASE_URL` decides which database is migrated. There is no connection string in
`alembic.ini` on purpose.

## Read the generated migration

Autogenerate is a diff, not an oracle. It reliably misses:

- **Column renames.** It sees a dropped column and a new one, and will happily generate
  `drop_column` + `add_column`, which is data loss. Rewrite it as `alter_column`.
- **`server_default` changes**, unless `compare_server_default` is on.
- **Anything CHECK-constraint shaped**, which this schema uses for reminder frequency
  and day ranges.

## Deployment

`docker-entrypoint.sh` runs `alembic upgrade head` and only then execs uvicorn, so a
failed migration is a failed deploy rather than a server running against a schema that
does not match the code.

The better home for this is Render's `preDeployCommand`, which runs once per deploy
instead of once per instance — but that is a paid-plan feature. The difference only
starts to matter above one replica, which the free plan does not offer; at that point
the fix is to move the line into `preDeployCommand`, not to add locking to the script.
