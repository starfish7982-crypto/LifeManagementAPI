def test_monthly_reminder_requires_day_of_month(client):
    resp = client.post("/reminders", json={"title": "Rent", "frequency": "monthly"})
    assert resp.status_code == 422


def test_once_reminder_requires_on_date(client):
    resp = client.post("/reminders", json={"title": "Visa", "frequency": "once"})
    assert resp.status_code == 422


def test_yearly_requires_both_day_and_month(client):
    resp = client.post(
        "/reminders", json={"title": "Insurance", "frequency": "yearly", "day_of_month": 3}
    )
    assert resp.status_code == 422


def test_create_returns_computed_next_due(client):
    resp = client.post(
        "/reminders", json={"title": "Rent", "frequency": "monthly", "day_of_month": 1}
    )
    assert resp.status_code == 201
    assert resp.json()["next_due"] is not None


def test_day_of_month_out_of_range_is_rejected(client):
    resp = client.post(
        "/reminders", json={"title": "Bad", "frequency": "monthly", "day_of_month": 32}
    )
    assert resp.status_code == 422


def test_due_within_days_filter(client):
    client.post("/reminders", json={"title": "Soon", "frequency": "once", "on_date": "2026-03-03"})
    client.post("/reminders", json={"title": "Later", "frequency": "once", "on_date": "2026-09-01"})

    resp = client.get("/reminders?today=2026-03-01&due_within_days=7")
    titles = [r["title"] for r in resp.json()]
    assert titles == ["Soon"]


def test_active_only_filter(client):
    client.post(
        "/reminders",
        json={"title": "Paused", "frequency": "monthly", "day_of_month": 1, "active": False},
    )
    assert client.get("/reminders?active_only=true").json() == []
    assert len(client.get("/reminders?active_only=false").json()) == 1


def test_delete_then_404(client):
    created = client.post(
        "/reminders", json={"title": "X", "frequency": "monthly", "day_of_month": 2}
    ).json()
    assert client.delete(f"/reminders/{created['id']}").status_code == 204
    assert client.get(f"/reminders/{created['id']}").status_code == 404
