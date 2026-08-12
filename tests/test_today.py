from app.routers.today import _format_summary
from app.schemas import TodayOut


def test_today_combines_todos_and_reminders(client):
    client.post("/todos", json={"title": "Call bank", "due_date": "2026-03-02"})
    client.post("/reminders", json={"title": "Rent", "frequency": "monthly", "day_of_month": 2})

    resp = client.get("/today?day=2026-03-02")
    assert resp.status_code == 200

    body = resp.json()
    assert [t["title"] for t in body["todos"]] == ["Call bank"]
    assert [r["title"] for r in body["reminders_due"]] == ["Rent"]
    assert body["calendar_events"] == []  # calendar disabled in tests


def test_today_excludes_completed_todos(client):
    created = client.post("/todos", json={"title": "Done thing", "due_date": "2026-03-02"}).json()
    client.patch(f"/todos/{created['id']}", json={"done": True})

    assert client.get("/today?day=2026-03-02").json()["todos"] == []


def test_today_excludes_reminders_not_due_on_that_day(client):
    client.post("/reminders", json={"title": "Rent", "frequency": "monthly", "day_of_month": 2})
    assert client.get("/today?day=2026-03-05").json()["reminders_due"] == []


def test_notify_reports_when_nothing_is_due(client):
    resp = client.post("/today/notify?day=2026-03-02")
    assert resp.status_code == 200
    assert "Nothing due" in resp.json()["detail"]


def test_notify_reports_failure_when_telegram_disabled(client):
    client.post("/todos", json={"title": "Something", "due_date": "2026-03-02"})
    resp = client.post("/today/notify?day=2026-03-02")
    assert "could not be delivered" in resp.json()["detail"]


def test_summary_escapes_html_in_titles():
    """parse_mode=HTML means unescaped user input would corrupt the message."""
    payload = TodayOut.model_validate(
        {
            "date": "2026-03-02",
            "todos": [
                {
                    "id": 1,
                    "title": "<b>rent</b> & fees",
                    "due_date": None,
                    "done": False,
                    "source": "manual",
                    "created_at": "2026-03-02T00:00:00Z",
                }
            ],
            "reminders_due": [],
            "calendar_events": [],
        }
    )
    text = _format_summary(payload)
    assert "&lt;b&gt;rent&lt;/b&gt; &amp; fees" in text
