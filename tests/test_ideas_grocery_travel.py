"""The three screens ported last: ideas, groceries and recipes, and the trip.

Each section ends with an isolation test. `other_client` shares a database with
`client` on purpose — two users in two databases would pass an unscoped query too.
"""

import pytest

# --------------------------------------------------------------------------- ideas


def test_ideas_come_back_newest_first(client):
    for text in ["first", "second", "third"]:
        client.post("/ideas", json={"text": text})
    assert [i["text"] for i in client.get("/ideas").json()] == ["third", "second", "first"]


def test_an_idea_can_be_edited_and_deleted(client):
    idea = client.post("/ideas", json={"text": "Figgy 的訓練按鈕"}).json()
    client.put(f"/ideas/{idea['id']}", json={"text": "Figgy 的訓練按鈕", "note": "點了給零食"})
    assert client.get("/ideas").json()[0]["note"] == "點了給零食"

    assert client.delete(f"/ideas/{idea['id']}").status_code == 204
    assert client.get("/ideas").json() == []


def test_ideas_are_private(client, other_client):
    idea = client.post("/ideas", json={"text": "mine"}).json()
    assert other_client.get("/ideas").json() == []
    assert other_client.put(f"/ideas/{idea['id']}", json={"text": "theirs"}).status_code == 404
    assert other_client.delete(f"/ideas/{idea['id']}").status_code == 404


# ------------------------------------------------------------------------ shopping


def test_shopping_keeps_insertion_order(client):
    for text in ["牛番茄", "蒜頭", "薑片"]:
        client.post("/grocery/shopping", json={"text": text})
    assert [i["text"] for i in client.get("/grocery/shopping").json()] == ["牛番茄", "蒜頭", "薑片"]


def test_ticking_an_item_does_not_wipe_its_quantity(client):
    """`exclude_unset` on the PATCH. The same rule the todos router needed, and the
    same regression if it goes missing."""
    item = client.post("/grocery/shopping", json={"text": "白蘿蔔", "quantity": "適量"}).json()
    client.patch(f"/grocery/shopping/{item['id']}", json={"done": True})

    after = client.get("/grocery/shopping").json()[0]
    assert after["done"] is True
    assert after["quantity"] == "適量"


def test_clearing_removes_only_bought_items_by_default(client):
    bought = client.post("/grocery/shopping", json={"text": "蔥", "done": True}).json()
    client.post("/grocery/shopping", json={"text": "洗碗錠"})
    client.patch(f"/grocery/shopping/{bought['id']}", json={"done": True})

    assert client.delete("/grocery/shopping").status_code == 204
    assert [i["text"] for i in client.get("/grocery/shopping").json()] == ["洗碗錠"]

    assert client.delete("/grocery/shopping?done_only=false").status_code == 204
    assert client.get("/grocery/shopping").json() == []


def test_clearing_is_scoped_to_the_caller(client, other_client):
    """A bulk DELETE is the statement where a missing user_id predicate is worst: it
    would empty every account's list at once, silently, with a 204."""
    client.post("/grocery/shopping", json={"text": "mine"})
    other_client.post("/grocery/shopping", json={"text": "theirs"})

    client.delete("/grocery/shopping?done_only=false")
    assert [i["text"] for i in other_client.get("/grocery/shopping").json()] == ["theirs"]


# ------------------------------------------------------------------------- recipes


def test_a_recipe_round_trips(client):
    payload = {
        "name": "烤雞胸肉(嫩)",
        "ingredients": "雞胸肉300g, 中等厚度",
        "steps": "350F 40-50分鐘, 關火靜置10分鐘",
        "temp": "350F",
        "video_url": "https://youtu.be/PUCLToWjMKs",
    }
    created = client.post("/grocery/recipes", json=payload).json()
    assert created["name"] == payload["name"]
    assert created["video_url"] == payload["video_url"]


@pytest.mark.parametrize("bad", ["javascript:alert(1)", "data:text/html,<script>", "ftp://x"])
def test_a_recipe_link_must_be_http(client, bad):
    """The field is rendered as a link the user clicks. `javascript:` in an href is
    script execution on this origin — which is what would make the token in
    localStorage readable. React escapes text, not URLs."""
    r = client.post("/grocery/recipes", json={"name": "x", "video_url": bad})
    assert r.status_code == 422


def test_recipes_are_private(client, other_client):
    recipe = client.post("/grocery/recipes", json={"name": "煎牛排"}).json()
    assert other_client.get("/grocery/recipes").json() == []
    assert other_client.delete(f"/grocery/recipes/{recipe['id']}").status_code == 404


# ---------------------------------------------------------------------- meal ideas


def test_meal_ideas_round_trip_in_category_name_order(client):
    client.post(
        "/grocery/meal-ideas", json={"category": "Pork", "name": "炒飯", "status": "常做"}
    )
    chicken = client.post(
        "/grocery/meal-ideas",
        json={"category": "Chicken", "name": "烤雞胸", "status": "想試"},
    ).json()

    ideas = client.get("/grocery/meal-ideas").json()
    assert [(idea["category"], idea["name"]) for idea in ideas] == [
        ("Chicken", "烤雞胸"),
        ("Pork", "炒飯"),
    ]

    client.put(
        f"/grocery/meal-ideas/{chicken['id']}",
        json={"category": "Chicken", "name": "烤雞腿", "status": "常做"},
    )
    assert client.get("/grocery/meal-ideas").json()[0]["status"] == "常做"


def test_meal_ideas_are_private(client, other_client):
    idea = client.post(
        "/grocery/meal-ideas", json={"category": "Fish", "name": "鮭魚", "status": "常做"}
    ).json()
    assert other_client.get("/grocery/meal-ideas").json() == []
    assert other_client.delete(f"/grocery/meal-ideas/{idea['id']}").status_code == 404


# -------------------------------------------------------------------------- travel


def test_no_trip_returns_null_not_404(client):
    assert client.get("/travel").json() is None


def test_a_trip_is_created_by_its_first_lodging(client):
    """Adding a hotel before filling in the dates is a reasonable order to work in."""
    client.post("/travel/lodgings", json={"name": "Residence Inn", "check_in": "2026-08-20"})
    trip = client.get("/travel").json()
    assert trip is not None
    assert [x["name"] for x in trip["lodgings"]] == ["Residence Inn"]


def test_lodgings_are_ordered_by_check_in(client):
    client.post("/travel/lodgings", json={"name": "Second", "check_in": "2026-08-22"})
    client.post("/travel/lodgings", json={"name": "First", "check_in": "2026-08-20"})
    assert [x["name"] for x in client.get("/travel").json()["lodgings"]] == ["First", "Second"]


def test_the_trip_dates_must_make_sense(client):
    r = client.put("/travel", json={"start_date": "2026-08-23", "end_date": "2026-08-20"})
    assert r.status_code == 422


def test_packing_items_toggle_and_keep_order(client):
    ids = [
        client.post("/travel/packing", json={"text": t}).json()["id"]
        for t in ["護照", "綠卡", "牙刷"]
    ]
    client.patch(f"/travel/packing/{ids[1]}?done=true")

    packing = client.get("/travel").json()["packing"]
    assert [p["text"] for p in packing] == ["護照", "綠卡", "牙刷"]
    assert [p["done"] for p in packing] == [False, True, False]


def test_each_traveller_can_have_a_separate_packing_checklist(client, other_client):
    sally = client.post("/travel/packing-lists", json={"name": "Sally"}).json()
    eason = client.post("/travel/packing-lists", json={"name": "Eason"}).json()
    client.post(f"/travel/packing?packing_list_id={sally['id']}", json={"text": "護照"})
    client.post(f"/travel/packing?packing_list_id={eason['id']}", json={"text": "相機"})

    trip = client.get("/travel").json()
    lists = {packing_list["name"]: packing_list["items"] for packing_list in trip["packing_lists"]}
    assert [item["text"] for item in lists["Sally"]] == ["護照"]
    assert [item["text"] for item in lists["Eason"]] == ["相機"]
    assert other_client.put(f"/travel/packing-lists/{sally['id']}", json={"name": "Mine"}).status_code == 404


def test_packing_items_can_be_reordered_only_within_their_own_checklist(client):
    packing_list = client.post("/travel/packing-lists", json={"name": "Sally"}).json()
    ids = [
        client.post(f"/travel/packing?packing_list_id={packing_list['id']}", json={"text": text}).json()["id"]
        for text in ["護照", "外套", "相機"]
    ]
    response = client.put(
        f"/travel/packing-lists/{packing_list['id']}/items/order",
        json={"ids": [ids[2], ids[0], ids[1]]},
    )
    assert response.status_code == 200
    assert [item["position"] for item in response.json()] == [0, 1, 2]
    trip = client.get("/travel").json()
    result = next(row for row in trip["packing_lists"] if row["id"] == packing_list["id"])
    assert [item["text"] for item in result["items"]] == ["相機", "護照", "外套"]


def test_deleting_the_trip_takes_its_children(client):
    client.post("/travel/lodgings", json={"name": "Hotel"})
    client.post("/travel/packing", json={"text": "護照"})

    assert client.delete("/travel").status_code == 204
    assert client.get("/travel").json() is None

    # And a fresh trip starts empty rather than inheriting the old rows.
    client.put("/travel", json={"license_plate": "LGE5488"})
    trip = client.get("/travel").json()
    assert trip["lodgings"] == [] and trip["packing"] == []


def test_another_users_trip_is_unreachable(client, other_client):
    lodging = client.post("/travel/lodgings", json={"name": "Residence Inn"}).json()
    packing = client.post("/travel/packing", json={"text": "護照"}).json()

    assert other_client.get("/travel").json() is None
    # No trip of their own yet, so these 404 on the trip lookup.
    assert other_client.delete(f"/travel/lodgings/{lodging['id']}").status_code == 404
    assert other_client.patch(f"/travel/packing/{packing['id']}?done=true").status_code == 404


def test_a_lodging_cannot_be_reached_through_another_trip(client, other_client):
    """The sharper version: the attacker has a trip, so the trip lookup succeeds and
    only the trip_id predicate on the child stands between them and the row."""
    victim = client.post("/travel/lodgings", json={"name": "private"}).json()
    other_client.put("/travel", json={"license_plate": "THEIRS"})

    r = other_client.put(f"/travel/lodgings/{victim['id']}", json={"name": "overwritten"})
    assert r.status_code == 404
    assert client.get("/travel").json()["lodgings"][0]["name"] == "private"


def test_trip_expenses_total_fields_round_trip_and_stay_private(client, other_client):
    created = client.post(
        "/travel/expenses",
        json={
            "merchant": "Museum",
            "amount": "24.50",
            "spent_at": "2026-08-20",
            "category": "Tickets",
            "note": "Two entries",
        },
    )
    assert created.status_code == 201
    expense = created.json()
    assert expense["amount"] == "24.50"
    assert expense["has_receipt"] is False
    assert client.get("/travel").json()["expenses"][0]["merchant"] == "Museum"

    other_client.put("/travel", json={"license_plate": "THEIRS"})
    assert other_client.put(
        f"/travel/expenses/{expense['id']}",
        json={"merchant": "No", "amount": "1", "spent_at": "2026-08-20"},
    ).status_code == 404


def test_receipt_upload_creates_an_editable_expense_and_is_not_public(client, other_client):
    # A minimal PNG header is enough for the route test: OCR is optional and an
    # unrecognised receipt deliberately comes back as a zero-dollar draft.
    uploaded = client.post(
        "/travel/expenses/scan",
        files={"receipt": ("taxi.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert uploaded.status_code == 201, uploaded.text
    expense = uploaded.json()
    assert expense["has_receipt"] is True
    assert expense["receipt_filename"] == "taxi.png"

    image = client.get(f"/travel/expenses/{expense['id']}/receipt")
    assert image.status_code == 200
    assert image.content.startswith(b"\x89PNG")

    other_client.put("/travel", json={"license_plate": "THEIRS"})
    assert other_client.get(f"/travel/expenses/{expense['id']}/receipt").status_code == 404


# ---------------------------------------------------------------- travel benefits


def test_travel_benefits_are_ordered_by_expiry_and_private(client, other_client):
    later = client.post(
        "/travel/benefits",
        json={"card_name": "Later card", "benefit": "credit", "expires_at": "2027-08-01"},
    ).json()
    client.post(
        "/travel/benefits",
        json={"card_name": "Soon card", "benefit": "night", "expires_at": "2026-09-01"},
    )

    assert [benefit["card_name"] for benefit in client.get("/travel/benefits").json()] == [
        "Soon card",
        "Later card",
    ]
    assert other_client.get("/travel/benefits").json() == []
    assert other_client.delete(f"/travel/benefits/{later['id']}").status_code == 404


def test_lodging_contact_details_and_travel_benefit_edits_round_trip(client):
    lodging = client.post(
        "/travel/lodgings",
        json={
            "name": "Residence Inn",
            "check_in": "2026-08-20",
            "check_out": "2026-08-22",
            "address": "1 King St, Toronto",
            "confirmation_number": "ABC-1234",
            "phone": "+1 416 555 0100",
            "details": "Breakfast included",
        },
    ).json()
    assert lodging["address"] == "1 King St, Toronto"
    assert client.get("/travel").json()["lodgings"][0]["confirmation_number"] == "ABC-1234"

    benefit = client.post("/travel/benefits", json={"card_name": "Card", "benefit": "night"}).json()
    changed = client.put(
        f"/travel/benefits/{benefit['id']}",
        json={"card_name": "Updated card", "benefit": "credit", "expires_at": "2027-08-01"},
    )
    assert changed.status_code == 200
    assert changed.json()["card_name"] == "Updated card"
