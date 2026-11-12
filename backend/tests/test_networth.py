from datetime import date, datetime, timedelta

from tests.helpers import make_xlsx, row


def _account(client, name="Dhan", type="equity"):
    r = client.post("/api/accounts", json={"name": name, "type": type})
    assert r.status_code == 201, r.text
    return r.json()


def _snap(client, account_id, as_of, value, invested=None):
    body = {"as_of": as_of, "value": value}
    if invested is not None:
        body["invested"] = invested
    r = client.post(f"/api/accounts/{account_id}/snapshots", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def test_empty_net_worth(client):
    nw = client.get("/api/networth").json()
    assert nw["total"] == 0 and nw["history"] == [] and nw["by_type"] == [] and nw["as_of"] is None
    assert nw["invested"] is None and nw["gain"] is None


def test_latest_value_per_account_makes_the_total(client):
    dhan, bank = _account(client), _account(client, "HDFC", "cash")
    _snap(client, dhan["id"], "2026-08-01", 100000, 90000)
    _snap(client, dhan["id"], "2026-09-01", 120000, 95000)
    _snap(client, bank["id"], "2026-09-02", 50000)
    nw = client.get("/api/networth").json()
    assert nw["total"] == 170000
    assert nw["as_of"] == "2026-09-02"
    assert nw["invested"] == 95000 and nw["gain"] == 25000  # only accounts that report invested
    assert {t["type"]: t["total"] for t in nw["by_type"]} == {"equity": 120000, "cash": 50000}
    assert round(sum(t["share"] for t in nw["by_type"]), 6) == 1


def test_same_day_entry_replaces_the_first(client):
    acc = _account(client)
    _snap(client, acc["id"], "2026-09-01", 100)
    _snap(client, acc["id"], "2026-09-01", 150)
    snaps = client.get(f"/api/accounts/{acc['id']}/snapshots").json()
    assert [s["value"] for s in snaps] == [150]


def test_history_carries_each_account_forward(client):
    a, b = _account(client), _account(client, "HDFC", "cash")
    _snap(client, a["id"], "2026-01-10", 100)
    _snap(client, b["id"], "2026-03-05", 40)
    _snap(client, a["id"], "2026-03-20", 130)
    history = {h["month"]: h["total"] for h in client.get("/api/networth").json()["history"]}
    assert history["2026-01"] == 100
    assert history["2026-02"] == 100  # nothing new: carried forward
    assert history["2026-03"] == 170  # 130 + 40
    assert list(history)[-1] >= "2026-03"  # runs up to the current month


def test_archived_accounts_leave_the_total_but_keep_their_history(client):
    a, b = _account(client), _account(client, "Old PF", "debt")
    _snap(client, a["id"], "2026-09-01", 100)
    _snap(client, b["id"], "2026-09-01", 500)
    r = client.patch(f"/api/accounts/{b['id']}", json={"archived": True})
    assert r.json()["archived"] is True
    assert client.get("/api/networth").json()["total"] == 100
    assert len(client.get(f"/api/accounts/{b['id']}/snapshots").json()) == 1
    client.patch(f"/api/accounts/{b['id']}", json={"archived": False})
    assert client.get("/api/networth").json()["total"] == 600


def test_account_list_shows_latest_and_age(client):
    acc = _account(client)
    old = (date.today() - timedelta(days=40)).isoformat()
    _snap(client, acc["id"], old, 100, 80)
    listed = client.get("/api/accounts").json()[0]
    assert listed["value"] == 100 and listed["gain"] == 20 and listed["days_old"] == 40
    fresh = _account(client, "Empty", "other")
    assert [a for a in client.get("/api/accounts").json() if a["id"] == fresh["id"]][0]["value"] is None


def test_validation(client):
    assert client.post("/api/accounts", json={"name": "X", "type": "crypto"}).status_code == 422
    acc = _account(client)
    assert client.post("/api/accounts", json={"name": "Dhan", "type": "equity"}).status_code == 409
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    assert client.post(f"/api/accounts/{acc['id']}/snapshots", json={"as_of": tomorrow, "value": 1}).status_code == 422
    assert client.post(f"/api/accounts/{acc['id']}/snapshots", json={"as_of": "2026-01-01", "value": -5}).status_code == 422
    assert client.post("/api/accounts/999/snapshots", json={"as_of": "2026-01-01", "value": 5}).status_code == 404


def test_delete_snapshot_and_account(client):
    acc = _account(client)
    snap = _snap(client, acc["id"], "2026-09-01", 100)
    assert client.delete(f"/api/snapshots/{snap['id']}").status_code == 204
    assert client.get("/api/networth").json()["total"] == 0
    _snap(client, acc["id"], "2026-09-01", 100)
    assert client.delete(f"/api/accounts/{acc['id']}").status_code == 204
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/networth").json()["total"] == 0


def test_contributions_come_from_investment_transfers(client, tmp_path):
    rows = [
        row(1, "Investments", "SIP", 25000) | {"ts": datetime(2026, 8, 3, 9)},
        row(1, "Investments", "SIP", 25000) | {"ts": datetime(2026, 9, 3, 9)},
        row(1, "Food", "Lunch", 300) | {"ts": datetime(2026, 9, 5, 9)},
    ]
    path = make_xlsx(tmp_path / "x.xlsx", rows)
    with open(path, "rb") as f:
        sha = client.post("/api/imports", files={"file": ("x.xlsx", f)}).json()["sha256"]
    assert client.post(f"/api/imports/{sha}/commit").status_code in (200, 201)
    nw = client.get("/api/networth").json()
    assert {c["month"]: c["total"] for c in nw["contributions"]} == {"2026-08": 25000, "2026-09": 25000}
    assert nw["contributed_total"] == 50000
