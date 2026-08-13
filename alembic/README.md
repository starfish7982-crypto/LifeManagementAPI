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

Render runs `alembic upgrade head` before starting the app; see `preDeployCommand` in
`render.yaml`. Making it a pre-deploy step rather than part of the container's start
command matters once more than one instance runs: every replica would otherwise race
to apply the same migration on boot.
