def test_health_needs_no_api_key(client):
    client.headers.pop("X-API-Key")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_protected_route_rejects_missing_key(client):
    client.headers.pop("X-API-Key")
    assert client.get("/todos").status_code == 401


def test_protected_route_rejects_wrong_key(client):
    client.headers.update({"X-API-Key": "not-the-key"})
    assert client.get("/todos").status_code == 401


def test_openapi_schema_is_served(client):
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    assert "/assets/snapshots" in resp.json()["paths"]
