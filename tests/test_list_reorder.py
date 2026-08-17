"""Reordering list rows.

The endpoint takes the whole order rather than a move instruction, so most of what is
worth testing is what it refuses: a set of ids that no longer matches the list.
"""

COLUMNS = {"name": "menu", "icon": "🍳", "columns": ["dish"], "position": 0}


def make_list(client, rows=("a", "b", "c")):
    list_id = client.post("/lists", json=COLUMNS).json()["id"]
    ids = [
        client.post(f"/lists/{list_id}/items", json={"values": [r]}).json()["id"] for r in rows
    ]
    return list_id, ids


def order_of(client, list_id):
    return [row["values"][0] for row in client.get(f"/lists/{list_id}").json()["items"]]


def test_rows_can_be_reordered(client):
    list_id, ids = make_list(client)
    assert order_of(client, list_id) == ["a", "b", "c"]

    r = client.put(f"/lists/{list_id}/items/order", json={"ids": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200
    assert order_of(client, list_id) == ["c", "a", "b"]


def test_positions_are_renumbered_from_zero(client):
    """Gaps would still sort correctly, but they accumulate — and a later insert that
    computes max()+1 would then sit further from its neighbours each time."""
    list_id, ids = make_list(client)
    client.put(f"/lists/{list_id}/items/order", json={"ids": list(reversed(ids))})

    positions = [row["position"] for row in client.get(f"/lists/{list_id}").json()["items"]]
    assert positions == [0, 1, 2]


def test_reordering_is_idempotent(client):
    """Sending the full order means replaying the request changes nothing, which is
    what makes it safe when the network decides to deliver it twice."""
    list_id, ids = make_list(client)
    wanted = [ids[1], ids[2], ids[0]]

    client.put(f"/lists/{list_id}/items/order", json={"ids": wanted})
    client.put(f"/lists/{list_id}/items/order", json={"ids": wanted})
    assert order_of(client, list_id) == ["b", "c", "a"]


def test_a_missing_row_is_refused(client):
    """A short list means the client is working from a stale copy. Applying it would
    leave the unmentioned row at whatever position it happened to hold."""
    list_id, ids = make_list(client)
    r = client.put(f"/lists/{list_id}/items/order", json={"ids": ids[:2]})
    assert r.status_code == 409
    assert order_of(client, list_id) == ["a", "b", "c"]


def test_an_unknown_row_is_refused(client):
    list_id, ids = make_list(client)
    r = client.put(f"/lists/{list_id}/items/order", json={"ids": [*ids, 99999]})
    assert r.status_code == 409


def test_a_duplicated_row_is_refused(client):
    list_id, ids = make_list(client)
    r = client.put(f"/lists/{list_id}/items/order", json={"ids": [ids[0], ids[0], ids[1]]})
    assert r.status_code == 422


def test_a_row_from_another_list_is_refused(client):
    """Two lists of the same length would otherwise pass a naive length check."""
    first, first_ids = make_list(client)
    second_id = client.post("/lists", json={**COLUMNS, "name": "other"}).json()["id"]
    other_row = client.post(f"/lists/{second_id}/items", json={"values": ["x"]}).json()["id"]

    r = client.put(
        f"/lists/{first}/items/order", json={"ids": [first_ids[0], first_ids[1], other_row]}
    )
    assert r.status_code == 409


def test_another_users_list_cannot_be_reordered(client, other_client):
    list_id, ids = make_list(client)
    r = other_client.put(f"/lists/{list_id}/items/order", json={"ids": list(reversed(ids))})
    assert r.status_code == 404
    assert order_of(client, list_id) == ["a", "b", "c"]


def test_the_order_route_is_not_swallowed_by_the_item_route(client):
    """`/items/order` and `/items/{item_id}` overlap. FastAPI matches in registration
    order, so this passes only while the literal path is declared first."""
    list_id, ids = make_list(client)
    r = client.put(f"/lists/{list_id}/items/order", json={"ids": list(reversed(ids))})
    assert r.status_code == 200, "the literal /order path must win over /{item_id}"


def test_editing_a_row_still_works_after_the_literal_route(client):
    """The other half of that overlap: real ids must still reach the item handler."""
    list_id, ids = make_list(client)
    r = client.put(f"/lists/{list_id}/items/{ids[0]}", json={"values": ["renamed"]})
    assert r.status_code == 200
    assert order_of(client, list_id)[0] == "renamed"


# ------------------------------------------------------ reordering the lists

def make_lists(client, names=("a", "b", "c")):
    return [
        client.post("/lists", json={**COLUMNS, "name": n, "position": i}).json()["id"]
        for i, n in enumerate(names)
    ]


def names_of(client):
    return [x["name"] for x in client.get("/lists").json()]


def test_lists_can_be_reordered(client):
    ids = make_lists(client)
    assert names_of(client) == ["a", "b", "c"]

    r = client.put("/lists/order", json={"ids": [ids[2], ids[0], ids[1]]})
    assert r.status_code == 200
    assert names_of(client) == ["c", "a", "b"]


def test_dragging_a_list_to_the_front(client):
    """The motivating case: pull one list up to the top of the sidebar."""
    ids = make_lists(client, ("訂閱與年度費用", "每月固定支出", "每月預算"))
    moved = [ids[2], ids[0], ids[1]]
    client.put("/lists/order", json={"ids": moved})
    assert names_of(client)[0] == "每月預算"


def test_list_order_is_refused_when_it_does_not_match(client):
    ids = make_lists(client)
    assert client.put("/lists/order", json={"ids": ids[:2]}).status_code == 409
    assert client.put("/lists/order", json={"ids": [*ids, 999]}).status_code == 409
    assert client.put("/lists/order", json={"ids": [ids[0], ids[0], ids[1]]}).status_code == 422


def test_list_order_cannot_include_another_users_list(client, other_client):
    mine = make_lists(client, ("x", "y"))
    theirs = other_client.post("/lists", json={**COLUMNS, "name": "theirs"}).json()["id"]

    r = client.put("/lists/order", json={"ids": [mine[0], theirs]})
    assert r.status_code == 409
    assert names_of(client) == ["x", "y"]


def test_the_lists_order_route_is_not_read_as_a_list_id(client):
    """`/lists/order` and `/lists/{list_id}` overlap; the literal must be declared
    first or this request is parsed as a malformed id."""
    ids = make_lists(client)
    r = client.put("/lists/order", json={"ids": list(reversed(ids))})
    assert r.status_code == 200


def test_editing_a_list_still_works(client):
    """The other half of the overlap: real ids must still reach the list handler."""
    ids = make_lists(client)
    r = client.put(f"/lists/{ids[0]}", json={**COLUMNS, "name": "renamed"})
    assert r.status_code == 200
    assert "renamed" in names_of(client)
