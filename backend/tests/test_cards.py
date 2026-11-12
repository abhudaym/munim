from datetime import date, timedelta

import pytest

from munim.api.cards import statement_dates


@pytest.mark.parametrize(
    "day,today,last,nxt",
    [
        (20, date(2026, 11, 12), date(2026, 10, 20), date(2026, 11, 20)),
        (5, date(2026, 11, 12), date(2026, 11, 5), date(2026, 12, 5)),
        (12, date(2026, 11, 12), date(2026, 11, 12), date(2026, 12, 12)),  # today is statement day
        (31, date(2026, 11, 12), date(2026, 10, 31), date(2026, 11, 30)),  # short month clamps
        (31, date(2026, 3, 1), date(2026, 2, 28), date(2026, 3, 31)),
        (15, date(2026, 12, 20), date(2026, 12, 15), date(2027, 1, 15)),  # year rolls over
        (15, date(2026, 1, 3), date(2025, 12, 15), date(2026, 1, 15)),
    ],
)
def test_statement_dates(day, today, last, nxt):
    assert statement_dates(day, today) == (last, nxt)


def _card(client, name="HSBC Live+", day=20, due_days=18):
    r = client.post("/api/cards", json={"name": name, "statement_day": day, "due_days": due_days})
    assert r.status_code == 201, r.text
    return r.json()


def _bill(client, card_id, statement, amount, **extra):
    r = client.post(f"/api/cards/{card_id}/bills", json={"statement_date": statement, "amount": amount, **extra})
    assert r.status_code == 200, r.text
    return r.json()


def test_new_card_shows_next_statement_and_suggested_due(client):
    card = _card(client, day=20, due_days=18)
    last = date.fromisoformat(card["last_statement"])
    nxt = date.fromisoformat(card["next_statement"])
    assert last <= date.today() < nxt
    assert last.day == min(20, last.day) and card["days_to_statement"] == (nxt - date.today()).days
    assert card["suggested_due"] == (last + timedelta(days=18)).isoformat()
    assert card["last_bill"] is None and card["unpaid_total"] == 0


def test_due_date_defaults_from_the_card(client):
    card = _card(client, due_days=18)
    bill = _bill(client, card["id"], "2026-10-20", 12450)
    assert bill["due_date"] == "2026-11-07"
    assert bill["status"] in ("overdue", "paid", "due")


def test_status_and_unpaid_totals(client):
    card = _card(client)
    old = (date.today() - timedelta(days=60)).isoformat()
    recent = (date.today() - timedelta(days=3)).isoformat()
    _bill(client, card["id"], old, 5000)  # due long ago, unpaid
    paid = _bill(client, card["id"], (date.today() - timedelta(days=35)).isoformat(), 3000, paid_on=recent)
    latest = _bill(client, card["id"], recent, 8000, due_date=(date.today() + timedelta(days=10)).isoformat())
    assert paid["status"] == "paid" and latest["status"] == "due" and latest["days_to_due"] == 10
    listed = client.get("/api/cards").json()[0]
    assert listed["unpaid_total"] == 13000 and listed["unpaid_count"] == 2
    assert listed["last_bill"]["amount"] == 8000  # newest statement, not newest entered
    assert listed["next_due"] == (date.today() - timedelta(days=60) + timedelta(days=18)).isoformat()
    statuses = {b["amount"]: b["status"] for b in client.get(f"/api/cards/{card['id']}/bills").json()}
    assert statuses == {5000: "overdue", 3000: "paid", 8000: "due"}


def test_mark_paid_and_unpaid(client):
    card = _card(client)
    bill = _bill(client, card["id"], (date.today() - timedelta(days=2)).isoformat(), 900)
    r = client.patch(f"/api/bills/{bill['id']}", json={"paid": True}).json()
    assert r["status"] == "paid" and r["paid_on"] == date.today().isoformat()
    r = client.patch(f"/api/bills/{bill['id']}", json={"paid": False}).json()
    assert r["paid_on"] is None and r["status"] != "paid"
    r = client.patch(f"/api/bills/{bill['id']}", json={"amount": 950, "min_due": 50}).json()
    assert r["amount"] == 950 and r["min_due"] == 50


def test_same_statement_replaces(client):
    card = _card(client)
    stmt = (date.today() - timedelta(days=5)).isoformat()
    _bill(client, card["id"], stmt, 100)
    _bill(client, card["id"], stmt, 150)
    bills = client.get(f"/api/cards/{card['id']}/bills").json()
    assert [b["amount"] for b in bills] == [150]


def test_validation_and_cleanup(client):
    assert client.post("/api/cards", json={"name": "X", "statement_day": 0}).status_code == 422
    assert client.post("/api/cards", json={"name": "X", "statement_day": 32}).status_code == 422
    card = _card(client)
    assert client.post("/api/cards", json={"name": "HSBC Live+", "statement_day": 5}).status_code == 409
    future = (date.today() + timedelta(days=2)).isoformat()
    assert client.post(f"/api/cards/{card['id']}/bills", json={"statement_date": future, "amount": 1}).status_code == 422
    early = client.post(
        f"/api/cards/{card['id']}/bills",
        json={"statement_date": "2026-10-20", "amount": 1, "due_date": "2026-10-01"},
    )
    assert early.status_code == 422
    assert client.post("/api/cards/999/bills", json={"statement_date": "2026-10-20", "amount": 1}).status_code == 404
    bill = _bill(client, card["id"], "2026-10-20", 10)
    assert client.delete(f"/api/bills/{bill['id']}").status_code == 204
    _bill(client, card["id"], "2026-10-20", 10)
    assert client.delete(f"/api/cards/{card['id']}").status_code == 204
    assert client.get("/api/cards").json() == []


def test_archive_and_clear_due_days(client):
    card = _card(client, due_days=18)
    r = client.patch(f"/api/cards/{card['id']}", json={"due_days": None}).json()
    assert r["due_days"] is None and r["suggested_due"] is None
    r = client.patch(f"/api/cards/{card['id']}", json={"archived": True}).json()
    assert r["archived"] is True


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


def test_face_colour_and_last4(client):
    card = client.post(
        "/api/cards", json={"name": "Axis", "statement_day": 11, "color": "#1f3a8a", "last4": "4417"}
    ).json()
    assert card["color"] == "#1f3a8a" and card["last4"] == "4417" and card["image_url"] is None
    assert client.patch(f"/api/cards/{card['id']}", json={"color": "red"}).status_code == 422
    assert client.patch(f"/api/cards/{card['id']}", json={"last4": "12345"}).status_code == 422
    cleared = client.patch(f"/api/cards/{card['id']}", json={"last4": None}).json()
    assert cleared["last4"] is None and cleared["color"] == "#1f3a8a"


def test_card_image_upload_serve_replace_remove(client, data_dir):
    card = _card(client)
    r = client.put(f"/api/cards/{card['id']}/image", files={"file": ("card.png", PNG, "image/png")})
    assert r.status_code == 200, r.text
    url = r.json()["image_url"]
    assert client.get(url).content == PNG
    jpg = b"\xff\xd8\xff" + b"\x01" * 20
    url2 = client.put(f"/api/cards/{card['id']}/image", files={"file": ("c.jpg", jpg, "image/jpeg")}).json()["image_url"]
    assert url2 != url and client.get(url2).content == jpg
    assert len(list((data_dir / "cards").iterdir())) == 1  # the old file is gone
    assert client.delete(f"/api/cards/{card['id']}/image").json()["image_url"] is None
    assert client.get(f"/api/cards/{card['id']}/image").status_code == 404
    assert list((data_dir / "cards").iterdir()) == []


def test_card_image_rejects_non_images(client):
    card = _card(client)
    bad = client.put(f"/api/cards/{card['id']}/image", files={"file": ("x.png", b"<svg onload=1>", "image/png")})
    assert bad.status_code == 415
    big = client.put(f"/api/cards/{card['id']}/image", files={"file": ("x.png", PNG + b"0" * (3 * 1024 * 1024), "image/png")})
    assert big.status_code == 413


def test_old_cards_table_gains_the_new_columns(tmp_path):
    import sqlite3

    from munim.api.app import create_app

    data = tmp_path / "old"
    data.mkdir()
    conn = sqlite3.connect(data / "munim.db")
    conn.execute(
        "CREATE TABLE cards (id INTEGER PRIMARY KEY, name VARCHAR(100) UNIQUE, statement_day INTEGER, "
        "due_days INTEGER, created_at DATETIME, archived_at DATETIME)"
    )
    conn.execute("INSERT INTO cards (name, statement_day) VALUES ('Axis Amex', 11)")
    conn.commit()
    conn.close()
    from fastapi.testclient import TestClient

    with TestClient(create_app(data, load_llm_from_env=False)) as c:
        listed = c.get("/api/cards").json()
        assert listed[0]["name"] == "Axis Amex" and listed[0]["color"] is None
