from decimal import Decimal


def test_create_and_read_snapshot(client, snapshot_payload):
    resp = client.post("/assets/snapshots", json=snapshot_payload)
    assert resp.status_code == 201

    body = resp.json()
    assert body["month"] == "2026-03-01"
    assert len(body["items"]) == 3
    # 4200 + 18500.50 + 10000
    assert Decimal(body["total"]) == Decimal("32700.50")

    fetched = client.get(f"/assets/snapshots/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]


def test_month_is_normalised_to_first_of_month(client, snapshot_payload):
    snapshot_payload["month"] = "2026-03-28"
    resp = client.post("/assets/snapshots", json=snapshot_payload)
    assert resp.json()["month"] == "2026-03-01"


def test_duplicate_month_returns_409(client, snapshot_payload):
    assert client.post("/assets/snapshots", json=snapshot_payload).status_code == 201
    duplicate = client.post("/assets/snapshots", json=snapshot_payload)
    assert duplicate.status_code == 409
    assert "already exists" in duplicate.json()["detail"]


def test_replacing_items_deletes_the_old_rows(client, snapshot_payload):
    created = client.post("/assets/snapshots", json=snapshot_payload).json()

    resp = client.put(
        f"/assets/snapshots/{created['id']}",
        json={
            "month": "2026-03-01",
            "note": "revised",
            "items": [{"name": "Checking", "category": "cash", "amount": "1.00"}],
        },
    )
    assert resp.status_code == 200
    assert len(resp.json()["items"]) == 1
    assert Decimal(resp.json()["total"]) == Decimal("1.00")


def test_category_breakdown_aggregates_in_sql(client, snapshot_payload):
    created = client.post("/assets/snapshots", json=snapshot_payload).json()
    resp = client.get(f"/assets/snapshots/{created['id']}/categories")
    assert resp.status_code == 200

    totals = {row["category"]: Decimal(row["total"]) for row in resp.json()}
    assert totals == {"cash": Decimal("14200.00"), "investments": Decimal("18500.50")}
    # Ordered by total, descending.
    assert resp.json()[0]["category"] == "investments"


def test_delete_cascades_and_then_404s(client, snapshot_payload):
    created = client.post("/assets/snapshots", json=snapshot_payload).json()
    assert client.delete(f"/assets/snapshots/{created['id']}").status_code == 204
    assert client.get(f"/assets/snapshots/{created['id']}").status_code == 404


def test_currency_is_upper_cased(client, snapshot_payload):
    snapshot_payload["items"] = [
        {"name": "TW bank", "category": "cash", "amount": "100.00", "currency": "twd"}
    ]
    resp = client.post("/assets/snapshots", json=snapshot_payload)
    assert resp.json()["items"][0]["currency"] == "TWD"


def test_limit_is_capped(client):
    assert client.get("/assets/snapshots?limit=9999").status_code == 422


def test_unknown_snapshot_returns_404(client):
    assert client.get("/assets/snapshots/424242").status_code == 404
