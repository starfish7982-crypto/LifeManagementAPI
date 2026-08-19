#!/usr/bin/env python3
"""Copy the local trip packing checklists into a deployed LifeManagement account.

Run this on the computer that contains ``life.db``.  It uses the normal authenticated
API instead of a direct database connection, so a hosted database password is never
needed and the import works whether Render uses Postgres or SQLite.

Example:
    ./.venv/bin/python scripts/import_packing_lists.py \
      --api https://life-management-api-jkje.onrender.com \
      --username your-username

The password is prompted for and is not printed or stored. Re-running is safe: a list
with the same name is reused and an item with the same text in that list is skipped.
"""

from __future__ import annotations

import argparse
import getpass
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx


@dataclass(frozen=True)
class LocalList:
    name: str
    items: list[str]


def load_lists(database: Path) -> list[LocalList]:
    if not database.exists():
        raise RuntimeError(f"Local database not found: {database}")
    with sqlite3.connect(database) as connection:
        rows = connection.execute(
            """
            SELECT packing_lists.id, packing_lists.name
            FROM packing_lists
            JOIN trips ON trips.id = packing_lists.trip_id
            ORDER BY trips.updated_at DESC, packing_lists.position, packing_lists.id
            """
        ).fetchall()
        if not rows:
            raise RuntimeError("No local packing checklists found")
        return [
            LocalList(
                name=name,
                items=[
                    item[0]
                    for item in connection.execute(
                        "SELECT text FROM packing_items "
                        "WHERE packing_list_id = ? ORDER BY position, id",
                        (list_id,),
                    )
                ],
            )
            for list_id, name in rows
        ]


class Api:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self.client = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)
        response = self.client.post(
            "/auth/login", data={"username": username, "password": password}
        )
        response.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"

    def get(self, path: str):
        response = self.client.get(path)
        response.raise_for_status()
        return response.json()

    def send(self, method: str, path: str, payload: dict | None = None):
        response = self.client.request(method, path, json=payload)
        if response.status_code >= 400:
            detail = response.text[:300]
            raise RuntimeError(f"{method} {path} failed ({response.status_code}): {detail}")
        return response.json() if response.content else None


def import_lists(api: Api, source: list[LocalList]) -> None:
    initial_trip = api.get("/travel")
    remote = initial_trip or {"packing_lists": []}
    source_names = {packing_list.name for packing_list in source}

    for local in source:
        by_name = {packing_list["name"]: packing_list for packing_list in remote["packing_lists"]}
        remote_list = by_name.get(local.name)
        if remote_list is None:
            remote_list = api.send("POST", "/travel/packing-lists", {"name": local.name})
            print(f"+ Checklist: {local.name}")
            remote = api.get("/travel")
            by_name = {
                packing_list["name"]: packing_list for packing_list in remote["packing_lists"]
            }
            remote_list = by_name[local.name]

        existing_texts = {item["text"] for item in remote_list["items"]}
        for text in local.items:
            if text not in existing_texts:
                api.send(
                    "POST",
                    f"/travel/packing?packing_list_id={remote_list['id']}",
                    {"text": text},
                )
                print(f"  + {text}")

        # Refresh, then place imported rows in exactly the same order as the local
        # list. Any pre-existing remote-only rows stay at the end instead of vanishing.
        remote = api.get("/travel")
        remote_list = next(row for row in remote["packing_lists"] if row["id"] == remote_list["id"])
        item_id_by_text = {item["text"]: item["id"] for item in remote_list["items"]}
        wanted = [item_id_by_text[text] for text in local.items]
        wanted.extend(item["id"] for item in remote_list["items"] if item["id"] not in wanted)
        api.send("PUT", f"/travel/packing-lists/{remote_list['id']}/items/order", {"ids": wanted})

    # Creating the first remote checklist creates the app's compatibility default.
    # Remove only that newly-created, empty default; never touch a user's existing data.
    if initial_trip is None:
        remote = api.get("/travel")
        default = next(
            (
                row
                for row in remote["packing_lists"]
                if row["name"] == "出門 Checklist"
                and not row["items"]
                and row["name"] not in source_names
            ),
            None,
        )
        if default:
            api.send("DELETE", f"/travel/packing-lists/{default['id']}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Import local packing checklists into a deployed account"
    )
    parser.add_argument("--api", required=True, help="Deployed API base URL, without /app")
    parser.add_argument("--username", required=True, help="The deployed account username")
    parser.add_argument(
        "--database", type=Path, default=Path("life.db"), help="Local SQLite database path"
    )
    args = parser.parse_args()

    try:
        source = load_lists(args.database)
        print("Local checklists:", ", ".join(f"{row.name} ({len(row.items)})" for row in source))
        password = getpass.getpass("Deployed account password: ")
        api = Api(args.api, args.username, password)
        import_lists(api, source)
    except (RuntimeError, httpx.HTTPError) as error:
        print(f"Import stopped: {error}", file=sys.stderr)
        return 1

    print("Import complete. Refresh the deployed Travel page to verify the checklists.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
