"""The app shell is served, and it cannot shadow the API."""


def test_root_redirects_to_the_app(unauthenticated_client):
    r = unauthenticated_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/app/"


def test_app_serves_the_shell(unauthenticated_client):
    r = unauthenticated_client.get("/app/")
    assert r.status_code == 200
    assert "LifeManagement" in r.text
    assert 'id="auth"' in r.text


def test_static_assets_are_served(unauthenticated_client):
    for path in ["/app/app.js", "/app/api.js", "/app/views.js", "/app/ui.js", "/app/style.css"]:
        assert unauthenticated_client.get(path).status_code == 200, path


def test_the_mount_does_not_swallow_api_routes(unauthenticated_client):
    """Regression guard for the ordering rule in main.py.

    A StaticFiles mount claims every path beneath it. Mounted at "/" it would answer
    /todos and /docs before the routers ever saw them — the API would 404 with no error
    anywhere. Keeping the UI under /app makes the two namespaces disjoint; this asserts
    they stay that way.
    """
    assert unauthenticated_client.get("/health").json() == {"status": "ok"}
    assert unauthenticated_client.get("/todos").status_code == 401
    assert unauthenticated_client.get("/openapi.json").status_code == 200


def test_the_shell_ships_no_secrets(unauthenticated_client):
    """The UI is downloaded by anyone who visits. Nothing secret may be baked into it.

    Checks for the shapes a leaked secret actually takes, not for the word "password" —
    that appears legitimately all over a sign-in form, and a test that flags it would
    be noise rather than a check.
    """
    leaks = [
        "postgresql://",
        "postgres://",
        "jwt_secret",
        "eyJhbGciOi",  # the base64 prefix every HS256 JWT header starts with
        "neon.tech",
        "npg_",  # Neon's password prefix
    ]
    for path in ["/app/", "/app/app.js", "/app/api.js", "/app/views.js", "/app/ui.js"]:
        body = unauthenticated_client.get(path).text
        for needle in leaks:
            assert needle not in body, f"{needle!r} found in {path}"
