"""The savings goal, and the derived category list."""

GOAL = {
    "amount": "30000.00",
    "purpose": "緊急預備金- 1年生活費",
    "next_step": "股票佈局+36000生活費",
}


# ----------------------------------------------------------------------------- goal


def test_no_goal_returns_null_not_404(client):
    """An unset goal is a normal state, not a missing resource."""
    r = client.get("/assets/goal")
    assert r.status_code == 200
    assert r.json() is None


def test_set_then_read_back(client):
    assert client.put("/assets/goal", json=GOAL).status_code == 200
    body = client.get("/assets/goal").json()
    assert body["amount"] == "30000.00"
    assert body["purpose"] == GOAL["purpose"]


def test_put_is_idempotent_and_updates_in_place(client):
    client.put("/assets/goal", json=GOAL)
    client.put("/assets/goal", json={**GOAL, "amount": "45000.00"})

    body = client.get("/assets/goal").json()
    assert body["amount"] == "45000.00"
    # Still one goal, not two — the uniqueness is on user_id.
    assert client.put("/assets/goal", json=GOAL).status_code == 200


def test_amount_must_be_positive(client):
    assert client.put("/assets/goal", json={**GOAL, "amount": "0"}).status_code == 422
    assert client.put("/assets/goal", json={**GOAL, "amount": "-5"}).status_code == 422


def test_delete_is_idempotent(client):
    """204 whether or not a goal existed: the caller's intent is satisfied either way."""
    assert client.delete("/assets/goal").status_code == 204
    client.put("/assets/goal", json=GOAL)
    assert client.delete("/assets/goal").status_code == 204
    assert client.get("/assets/goal").json() is None


def test_goals_are_per_user(client, other_client):
    client.put("/assets/goal", json=GOAL)
    assert other_client.get("/assets/goal").json() is None

    other_client.put("/assets/goal", json={**GOAL, "amount": "999.00", "purpose": "theirs"})
    assert client.get("/assets/goal").json()["amount"] == "30000.00"


# ----------------------------------------------------------------------- categories


def test_categories_are_empty_before_any_snapshot(client):
    assert client.get("/assets/categories").json() == []


def test_categories_are_derived_from_snapshots(client, snapshot_payload):
    client.post("/assets/snapshots", json=snapshot_payload)
    # snapshot_payload has two cash items and one investments item.
    assert client.get("/assets/categories").json() == ["cash", "investments"]


def test_categories_are_deduplicated_and_ordered_by_use(client, snapshot_payload):
    client.post("/assets/snapshots", json=snapshot_payload)
    client.post(
        "/assets/snapshots",
        json={
            "month": "2026-04-01",
            "items": [
                {"name": "Brokerage", "category": "investments", "amount": "1.00"},
                {"name": "Roth", "category": "investments", "amount": "2.00"},
                {"name": "Crypto", "category": "crypto", "amount": "3.00"},
            ],
        },
    )
    # investments: 3 uses, cash: 2, crypto: 1.
    assert client.get("/assets/categories").json() == ["investments", "cash", "crypto"]


def test_categories_do_not_leak_between_users(client, other_client, snapshot_payload):
    client.post("/assets/snapshots", json=snapshot_payload)
    assert other_client.get("/assets/categories").json() == []


def test_a_category_disappears_when_its_last_item_does(client, snapshot_payload):
    """The consequence of deriving rather than storing, stated as a test so the
    behaviour is a decision rather than a surprise."""
    snapshot_id = client.post("/assets/snapshots", json=snapshot_payload).json()["id"]
    assert "investments" in client.get("/assets/categories").json()

    client.put(
        f"/assets/snapshots/{snapshot_id}",
        json={
            "month": snapshot_payload["month"],
            "items": [{"name": "Checking", "category": "cash", "amount": "1.00"}],
        },
    )
    assert client.get("/assets/categories").json() == ["cash"]
