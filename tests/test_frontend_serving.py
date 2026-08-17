"""The built UI is served, cached correctly, and cannot shadow the API.

Everything here needs `web/dist`, which only exists after `npm run build`. Rather than
fail on a checkout that has only ever run pytest, the module skips — the API is
deliberately able to run without a UI, and these tests describe the UI's delivery.
"""

import re

import pytest

from app.main import FRONTEND_DIR

pytestmark = pytest.mark.skipif(
    not FRONTEND_DIR.is_dir(),
    reason="web/dist not built; run `npm run build` in web/",
)


def test_root_redirects_to_the_app(unauthenticated_client):
    r = unauthenticated_client.get("/", follow_redirects=False)
    assert r.status_code in (302, 307)
    assert r.headers["location"] == "/app/"


def test_app_serves_the_shell(unauthenticated_client):
    r = unauthenticated_client.get("/app/")
    assert r.status_code == 200
    assert "LifeManagement" in r.text
    assert 'id="root"' in r.text


def test_every_asset_the_shell_references_is_served(unauthenticated_client):
    """The filenames are content hashes chosen at build time, so they cannot be
    hard-coded here. Reading them out of index.html is also the stronger check: it
    proves the file the browser will actually ask for is the one that exists."""
    html = unauthenticated_client.get("/app/").text
    referenced = re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', html)
    assert referenced, "index.html references no built assets"
    for path in referenced:
        assert unauthenticated_client.get(path).status_code == 200, path


def test_hashed_assets_are_cached_and_the_shell_is_not(unauthenticated_client):
    """A hashed filename can never change contents, so it is safe to keep for a year.
    index.html names those files, so a cached copy is how a browser ends up running
    last week's JavaScript."""
    html = unauthenticated_client.get("/app/")
    assert html.headers["cache-control"] == "no-cache"

    asset = re.search(r'(?:src|href)="(/app/assets/[^"]+)"', html.text)
    assert asset
    r = unauthenticated_client.get(asset.group(1))
    assert "immutable" in r.headers["cache-control"]
    assert "max-age=31536000" in r.headers["cache-control"]


def test_the_shell_revalidates_cheaply(unauthenticated_client):
    """no-cache still allows a 304, so the cost is one conditional request."""
    first = unauthenticated_client.get("/app/")
    again = unauthenticated_client.get("/app/", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304


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


def test_the_bundle_ships_no_secrets(unauthenticated_client):
    """The UI is downloaded by anyone who visits, so nothing secret may be built into
    it. Checks the shapes a leaked secret actually takes, not the word "password" —
    that appears legitimately all over a sign-in form."""
    html = unauthenticated_client.get("/app/").text
    paths = ["/app/"] + re.findall(r'(?:src|href)="(/app/assets/[^"]+)"', html)

    leaks = [
        "postgresql://",
        "postgres://",
        "jwt_secret",
        "eyJhbGciOi",  # the base64 prefix every HS256 JWT header starts with
        "neon.tech",
        "npg_",  # Neon's password prefix
    ]
    for path in paths:
        body = unauthenticated_client.get(path).text
        for needle in leaks:
            assert needle not in body, f"{needle!r} found in {path}"
