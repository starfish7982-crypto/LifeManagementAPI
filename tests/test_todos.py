def test_create_and_list(client):
    client.post("/todos", json={"title": "Renew registration", "due_date": "2026-03-10"})
    resp = client.get("/todos")
    assert resp.status_code == 200
    assert resp.json()[0]["title"] == "Renew registration"


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


def test_undated_todos_sort_after_dated_ones(client):
    client.post("/todos", json={"title": "someday"})
    client.post("/todos", json={"title": "tomorrow", "due_date": "2026-03-02"})
    assert [t["title"] for t in client.get("/todos").json()] == ["tomorrow", "someday"]


def test_empty_title_rejected(client):
    assert client.post("/todos", json={"title": ""}).status_code == 422
