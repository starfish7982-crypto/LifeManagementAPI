#!/usr/bin/env python3
"""Import the PowerShell app's JSON files into this API.

    python scripts/import_legacy.py ../LifeManagement-main/data --dry-run
    python scripts/import_legacy.py ../LifeManagement-main/data \
        --api https://life-management-api-jkje.onrender.com \
        --email you@example.com --register

It talks to the running API over HTTP rather than writing to the database directly.
That costs some speed for a few hundred rows and buys three things: the same validation
every other client gets, no second copy of the schema to keep in sync, and the ability
to run it against the deployed service from a laptop that cannot reach the database.

Re-running it is safe. Every step reads what is already there and skips matches, so a
run interrupted halfway can simply be run again — which matters more than it sounds,
because the first attempt at an import is almost never the last.

Shapes translated (old -> new):

    reminders   freq/day/month/date/daysBefore  -> frequency/day_of_month/
                                                   month_of_year/on_date/days_before
    assets      month "2026-01"                 -> month "2026-01-01"
                amount 25833 (int|float)        -> "25833.00" (decimal string)
                shortTermGoal                   -> PUT /assets/goal
    todos       text                            -> title
    lists       columns[] + items[].values[]    -> the same, as a real resource
"""

from __future__ import annotations

import argparse
import getpass
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import httpx

TIMEOUT = httpx.Timeout(60.0)  # Render's free tier cold-starts for up to ~50 seconds.


class ImportError_(RuntimeError):
    pass


# ------------------------------------------------------------------------ helpers


def money(value: Any) -> str:
    """Old data stores amounts as int or float; the API takes a 2dp decimal string.

    Going through str() before Decimal matters: Decimal(0.1) is
    0.1000000000000000055511151231257827, while Decimal("0.1") is exactly 0.1. The
    float was already imprecise, but this stops the error growing at the boundary.
    """
    return str(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def month_to_date(month: str) -> str:
    """'2026-01' -> '2026-01-01'. The API normalises to the 1st anyway; being explicit
    here means a malformed month fails in this script, with the file name to hand,
    rather than as a 422 from the server."""
    parts = month.split("-")
    if len(parts) != 2 or not (len(parts[0]) == 4 and len(parts[1]) == 2):
        raise ImportError_(f"Unrecognised month format: {month!r} (expected YYYY-MM)")
    return f"{month}-01"


def load(path: Path, name: str) -> dict:
    file = path / name
    if not file.exists():
        print(f"  ! {name} not found, skipping")
        return {}
    return json.loads(file.read_text(encoding="utf-8"))


class Client:
    def __init__(self, base: str, dry_run: bool):
        self.base = base.rstrip("/")
        self.dry_run = dry_run
        self.http = httpx.Client(timeout=TIMEOUT)
        self.token: str | None = None

    def register(self, email: str, password: str) -> bool:
        """Create the account if it is not there. Returns True if it was created.

        Safe to call when the account already exists: the API answers 409, which is
        treated as "fine, carry on and log in".
        """
        r = self.http.post(
            f"{self.base}/auth/register", json={"email": email, "password": password}
        )
        if r.status_code == 201:
            return True
        if r.status_code == 409:
            return False
        raise ImportError_(f"Could not register {email} ({r.status_code}): {r.text}")

    def login(self, email: str, password: str) -> None:
        r = self.http.post(
            f"{self.base}/auth/login", data={"username": email, "password": password}
        )
        if r.status_code == 401:
            # The API will not say whether the address is registered — that would make
            # /auth/login an account-enumeration oracle. Correct for the API, unhelpful
            # for the person running a script, so spell out both branches here.
            raise ImportError_(
                f"Login was rejected for {email}.\n"
                "The API does not distinguish a wrong password from an unknown account, "
                "so it is one of:\n"
                f"  - the password is wrong\n"
                f"  - no account exists for {email} yet\n"
                f"To tell them apart, POST /auth/register at {self.base}/docs — "
                "409 means the account exists, 201 means it did not and now does."
            )
        if r.status_code != 200:
            raise ImportError_(f"Login failed ({r.status_code}): {r.text}")
        self.token = r.json()["access_token"]
        self.http.headers["Authorization"] = f"Bearer {self.token}"

    def get(self, path: str) -> Any:
        r = self.http.get(f"{self.base}{path}")
        r.raise_for_status()
        return r.json()

    def send(self, method: str, path: str, payload: dict) -> Any:
        if self.dry_run:
            print(f"    DRY-RUN {method} {path}  {json.dumps(payload, ensure_ascii=False)[:110]}")
            return {"id": 0}
        r = self.http.request(method, f"{self.base}{path}", json=payload)
        if r.status_code >= 400:
            raise ImportError_(f"{method} {path} -> {r.status_code}: {r.text}")
        return r.json() if r.content else None


# ------------------------------------------------------------------------ importers


def import_assets(c: Client, data: dict) -> None:
    snapshots = data.get("snapshots", [])
    goal = data.get("shortTermGoal")
    print(f"\nAssets: {len(snapshots)} snapshots")

    existing = {s["month"] for s in c.get("/assets/snapshots")} if not c.dry_run else set()

    for snap in snapshots:
        month = month_to_date(snap["month"])
        if month in existing:
            print(f"  = {snap['month']} already imported, skipping")
            continue
        payload = {
            "month": month,
            "note": snap.get("note") or None,
            "items": [
                {
                    "name": item["name"],
                    "category": item["category"],
                    "amount": money(item["amount"]),
                    "currency": item.get("currency", "USD"),
                }
                for item in snap.get("items", [])
            ],
        }
        c.send("POST", "/assets/snapshots", payload)
        print(f"  + {snap['month']} ({len(payload['items'])} items)")

    if goal:
        # Always sent, never skipped: PUT /assets/goal is an upsert, so re-running
        # converges on the same single row instead of creating a second one. Printed as
        # "set" rather than "+" so a re-run does not read as though it created anything.
        c.send(
            "PUT",
            "/assets/goal",
            {
                "amount": money(goal["amount"]),
                "purpose": goal["purpose"],
                "next_step": goal.get("next") or None,
            },
        )
        print(f"  set goal: {money(goal['amount'])} — {goal['purpose']}")

    declared = set(data.get("categories", []))
    used = {item["category"] for snap in snapshots for item in snap.get("items", [])}
    if declared - used:
        # The old file kept a hand-maintained category list; this API derives categories
        # from the items that actually exist. Anything declared but never used has
        # nothing to derive it from, so say so rather than let it vanish silently.
        print(f"  ! not imported (declared but unused): {', '.join(sorted(declared - used))}")


def _reminder_identity(r: dict) -> tuple:
    """What makes two reminders the same one, for skip-on-re-run purposes.

    Title alone is not enough: this data has two reminders both called "Figgy -
    Revolution Plus 補貨", one in January and one in July. Deduplicating on the title
    would import only the first and silently drop the second.
    """
    return (
        r.get("title"),
        r.get("frequency") or r.get("freq"),
        r.get("day_of_month") if "day_of_month" in r else r.get("day"),
        r.get("month_of_year") if "month_of_year" in r else r.get("month"),
        str(r.get("on_date") or r.get("date") or ""),
    )


def import_reminders(c: Client, data: dict) -> None:
    reminders = data.get("reminders", [])
    print(f"\nReminders: {len(reminders)}")

    existing = (
        {_reminder_identity(r) for r in c.get("/reminders?active_only=false")}
        if not c.dry_run
        else set()
    )

    for rem in reminders:
        if _reminder_identity(rem) in existing:
            print(f"  = {rem['title'][:40]} already imported, skipping")
            continue

        freq = rem["freq"]
        payload: dict[str, Any] = {
            "title": rem["title"],
            "frequency": freq,
            "active": rem.get("active", True),
            "days_before": rem.get("daysBefore", 0),
            "note": rem.get("note") or None,
        }
        if freq == "once":
            payload["on_date"] = rem["date"]
        elif freq == "monthly":
            payload["day_of_month"] = rem["day"]
        elif freq == "yearly":
            payload["day_of_month"] = rem["day"]
            payload["month_of_year"] = rem["month"]
        else:
            raise ImportError_(f"Unknown frequency {freq!r} on reminder {rem['title']!r}")

        c.send("POST", "/reminders", payload)
        lead = f", {payload['days_before']}d lead" if payload["days_before"] else ""
        print(f"  + [{freq}{lead}] {rem['title'][:50]}")


def import_todos(c: Client, data: dict) -> None:
    todos = data.get("todos", [])
    print(f"\nTodos: {len(todos)}")

    existing = {t["title"] for t in c.get("/todos")} if not c.dry_run else set()

    for todo in todos:
        # The old field is `text`; the API calls it `title`.
        title = todo["text"]
        if title in existing:
            print(f"  = {title[:40]} already imported, skipping")
            continue
        # Old todos carry createdAt but no due date, and created_at is server-owned.
        c.send("POST", "/todos", {"title": title[:200], "done": todo.get("done", False)})
        print(f"  + {'[done] ' if todo.get('done') else ''}{title[:50]}")


def import_lists(c: Client, data: dict) -> None:
    tables = data.get("lists", [])
    print(f"\nLists: {len(tables)}")

    existing = {x["name"]: x for x in c.get("/lists")} if not c.dry_run else {}

    for position, table in enumerate(tables):
        name = table["name"]
        if name in existing:
            print(f"  = {name} already imported ({len(existing[name]['items'])} rows), skipping")
            continue

        created = c.send(
            "POST",
            "/lists",
            {
                "name": name,
                "icon": table.get("icon"),
                "columns": table["columns"],
                "position": position,
            },
        )
        width = len(table["columns"])
        rows = 0
        for item in table.get("items", []):
            values = [str(v) if v is not None else "" for v in item.get("values", [])]
            # Old rows are not guaranteed to match the header width; the API rejects
            # mismatches, so pad or trim here rather than failing the whole import.
            if len(values) < width:
                values += [""] * (width - len(values))
            elif len(values) > width:
                print(f"    ! row has {len(values)} values for {width} columns, trimming")
                values = values[:width]
            c.send("POST", f"/lists/{created['id']}/items", {"values": values})
            rows += 1
        print(f"  + {table.get('icon', '')} {name} ({width} columns, {rows} rows)")


# ----------------------------------------------------------------------------- main


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("data_dir", type=Path, help="the old app's data/ directory")
    parser.add_argument("--api", default="http://127.0.0.1:8000", help="API base URL")
    parser.add_argument("--email", help="account to import into")
    parser.add_argument(
        "--register",
        action="store_true",
        help="create the account first if it does not exist, then log in",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print what would be sent without sending it or logging in",
    )
    args = parser.parse_args()

    if not args.data_dir.is_dir():
        print(f"Not a directory: {args.data_dir}", file=sys.stderr)
        return 2

    client = Client(args.api, args.dry_run)

    if not args.dry_run:
        if not args.email:
            print("--email is required unless --dry-run is given", file=sys.stderr)
            return 2
        # Prompted, never taken as an argument: anything on the command line lands in
        # the shell history and in the process list.
        password = getpass.getpass(f"Password for {args.email}: ")
        if args.register:
            print(f"Checking for an account at {args.api} ...")
            if client.register(args.email, password):
                print(f"  created {args.email}")
            else:
                print(f"  {args.email} already exists, logging in")
        print(f"Logging in to {args.api} ...")
        client.login(args.email, password)

    try:
        import_assets(client, load(args.data_dir, "assets.json"))
        import_reminders(client, load(args.data_dir, "reminders.json"))
        import_todos(client, load(args.data_dir, "todos.json"))
        import_lists(client, load(args.data_dir, "lists.json"))
    except ImportError_ as exc:
        print(f"\nImport failed: {exc}", file=sys.stderr)
        return 1

    print("\nDone." if not args.dry_run else "\nDry run complete; nothing was sent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
