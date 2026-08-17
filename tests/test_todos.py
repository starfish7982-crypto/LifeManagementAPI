def test_create_and_list(client):
    created = client.post(
        "/todos", json={"title": "Renew registration", "due_date": "2026-03-10"}
    ).json()
    resp = client.get("/todos")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Renew registration"
    assert created["bucket"] == "today"
    assert created["position"] == 0


def test_patch_done_does_not_clear_due_date(client):
    """The regression PATCH exists to prevent: a partial update wiping omitted fields."""
    created = client.post("/todos", json={"title": "Pay bill", "due_date": "2026-03-10"}).json()

    patched = client.patch(f"/todos/{created['id']}", json={"done": True}).json()
    assert patched["done"] is True
    assert patched["due_date"] == "2026-03-10"


def test_patch_can_explicitly_null_a_field(client):
    created = client.post("/todos", json={"title": "Pay bill", "due_date": "2026-03-10"}).json()
    patched = client.patch(f"/todos/{created['id']}", json={"due_date": None}).json()
    assert patched["due_date"] is None


def test_done_filter(client):
    client.post("/todos", json={"title": "open"})
    done = client.post("/todos", json={"title": "closed"}).json()
    client.patch(f"/todos/{done['id']}", json={"done": True})

    assert [t["title"] for t in client.get("/todos?done=false").json()] == ["open"]
    assert [t["title"] for t in client.get("/todos?done=true").json()] == ["closed"]


def test_todos_keep_their_manual_lane_order_regardless_of_due_date(client):
    client.post("/todos", json={"title": "someday"})
    client.post("/todos", json={"title": "tomorrow", "due_date": "2026-03-02"})
    # A due date is context, not a competing hidden sort: the order is the one the
    # user sees and can change by dragging.
    assert [t["title"] for t in client.get("/todos").json()] == ["someday", "tomorrow"]


def test_empty_title_rejected(client):
    assert client.post("/todos", json={"title": ""}).status_code == 422


def test_todos_can_move_between_lanes_and_be_reordered(client):
    first = client.post("/todos", json={"title": "first"}).json()
    second = client.post("/todos", json={"title": "second"}).json()

    moved = client.patch(f"/todos/{second['id']}", json={"bucket": "later"})
    assert moved.status_code == 200
    assert moved.json()["bucket"] == "later"

    # Reordering names the complete lane, which makes its result deterministic.
    response = client.put("/todos/order", json={"bucket": "today", "ids": [first["id"]]})
    assert response.status_code == 200
    assert response.json()[0]["position"] == 0

    response = client.put("/todos/order", json={"bucket": "later", "ids": [second["id"]]})
    assert response.status_code == 200
    assert response.json()[0]["position"] == 0
