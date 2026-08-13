"""User-defined tables, including the invariant SQL cannot enforce."""

import pytest

SUBSCRIPTIONS = {
    "name": "訂閱與年度費用",
    "icon": "🔁",
    "columns": ["項目", "年費用(USD)", "付款方式", "續訂/到期日", "備註"],
}


def make_list(c, **overrides):
    r = c.post("/lists", json={**SUBSCRIPTIONS, **overrides})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_create_and_read_back(client):
    list_id = make_list(client)
    body = client.get(f"/lists/{list_id}").json()
    assert body["name"] == SUBSCRIPTIONS["name"]
    assert body["columns"] == SUBSCRIPTIONS["columns"]
    assert body["items"] == []


def test_duplicate_name_is_409(client):
    make_list(client)
    assert client.post("/lists", json=SUBSCRIPTIONS).status_code == 409


def test_a_list_needs_at_least_one_column(client):
    r = client.post("/lists", json={**SUBSCRIPTIONS, "columns": []})
    assert r.status_code == 422


def test_row_must_match_the_column_count(client):
    """The invariant no SQL constraint can express: len(values) == len(columns)."""
    list_id = make_list(client)

    too_few = client.post(f"/lists/{list_id}/items", json={"values": ["Spotify", "20"]})
    assert too_few.status_code == 422
    assert "5 values" in too_few.json()["detail"]

    too_many = client.post(
        f"/lists/{list_id}/items", json={"values": ["a", "b", "c", "d", "e", "f"]}
    )
    assert too_many.status_code == 422

    exact = client.post(
        f"/lists/{list_id}/items",
        json={"values": ["Spotify", "20", "Sally", "N/A", "Annually"]},
    )
    assert exact.status_code == 201


def test_rows_keep_their_insertion_order(client):
    list_id = make_list(client, columns=["item"])
    for name in ["first", "second", "third"]:
        client.post(f"/lists/{list_id}/items", json={"values": [name]})

    rows = client.get(f"/lists/{list_id}").json()["items"]
    assert [r["values"][0] for r in rows] == ["first", "second", "third"]
    assert [r["position"] for r in rows] == [0, 1, 2]


def test_deleting_a_row_does_not_reuse_its_position(client):
    """Positions come from max()+1, not count(), so a delete cannot cause a collision."""
    list_id = make_list(client, columns=["item"])
    ids = [
        client.post(f"/lists/{list_id}/items", json={"values": [n]}).json()["id"]
        for n in ["a", "b"]
    ]
    client.delete(f"/lists/{list_id}/items/{ids[0]}")

    new_row = client.post(f"/lists/{list_id}/items", json={"values": ["c"]}).json()
    assert new_row["position"] == 2

    rows = client.get(f"/lists/{list_id}").json()["items"]
    assert [r["values"][0] for r in rows] == ["b", "c"]


def test_changing_column_count_is_refused_while_rows_exist(client):
    list_id = make_list(client, columns=["a", "b"])
    client.post(f"/lists/{list_id}/items", json={"values": ["1", "2"]})

    widen = client.put(f"/lists/{list_id}", json={**SUBSCRIPTIONS, "columns": ["a", "b", "c"]})
    assert widen.status_code == 409

    # Renaming columns without changing the count is fine — the rows still line up.
    rename = client.put(f"/lists/{list_id}", json={**SUBSCRIPTIONS, "columns": ["x", "y"]})
    assert rename.status_code == 200
    assert rename.json()["items"][0]["values"] == ["1", "2"]


def test_changing_column_count_is_allowed_when_empty(client):
    list_id = make_list(client, columns=["a", "b"])
    r = client.put(f"/lists/{list_id}", json={**SUBSCRIPTIONS, "columns": ["a", "b", "c"]})
    assert r.status_code == 200


def test_deleting_a_list_deletes_its_rows(client):
    list_id = make_list(client, columns=["item"])
    client.post(f"/lists/{list_id}/items", json={"values": ["x"]})

    assert client.delete(f"/lists/{list_id}").status_code == 204
    assert client.get(f"/lists/{list_id}").status_code == 404


def test_lists_come_back_in_position_order(client):
    make_list(client, name="third", position=2)
    make_list(client, name="first", position=0)
    make_list(client, name="second", position=1)

    assert [x["name"] for x in client.get("/lists").json()] == ["first", "second", "third"]


# ------------------------------------------------------------------------ isolation


def test_another_users_list_is_invisible(client, other_client):
    list_id = make_list(client)

    assert other_client.get("/lists").json() == []
    assert other_client.get(f"/lists/{list_id}").status_code == 404
    assert other_client.delete(f"/lists/{list_id}").status_code == 404
    assert other_client.post(f"/lists/{list_id}/items", json={"values": []}).status_code == 404


def test_the_same_list_name_is_available_to_every_user(client, other_client):
    make_list(client)
    assert other_client.post("/lists", json=SUBSCRIPTIONS).status_code == 201


def test_a_row_cannot_be_reached_through_the_wrong_list(client, other_client):
    """Rows are addressed as /lists/{list_id}/items/{item_id}.

    If the row lookup ignored list_id, owning any list would be enough to edit any row
    in the database by guessing its id — the ownership check on the list in the path
    would pass while the row came from somewhere else entirely.
    """
    victim_list = make_list(client, columns=["secret"])
    victim_row = client.post(f"/lists/{victim_list}/items", json={"values": ["private"]}).json()

    attacker_list = other_client.post(
        "/lists", json={**SUBSCRIPTIONS, "name": "attacker", "columns": ["secret"]}
    ).json()["id"]

    r = other_client.put(
        f"/lists/{attacker_list}/items/{victim_row['id']}", json={"values": ["overwritten"]}
    )
    assert r.status_code == 404

    unchanged = client.get(f"/lists/{victim_list}").json()["items"][0]
    assert unchanged["values"] == ["private"]


@pytest.mark.parametrize("method", ["put", "delete"])
def test_another_users_row_cannot_be_touched(client, other_client, method):
    list_id = make_list(client, columns=["item"])
    row_id = client.post(f"/lists/{list_id}/items", json={"values": ["mine"]}).json()["id"]

    kwargs = {"json": {"values": ["theirs"]}} if method == "put" else {}
    resp = getattr(other_client, method)(f"/lists/{list_id}/items/{row_id}", **kwargs)
    assert resp.status_code == 404
