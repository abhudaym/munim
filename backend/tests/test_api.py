from __future__ import annotations

from tests.helpers import make_xlsx, row, sample_rows


def upload(client, tmp_path, rows, name="export.xlsx", dry_run=True):
    path = make_xlsx(tmp_path / name, rows)
    with open(path, "rb") as fh:
        return client.post(
            f"/api/imports?dry_run={'true' if dry_run else 'false'}",
            files={"file": (name, fh, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )


def load(client, tmp_path, rows=None):
    r = upload(client, tmp_path, rows or sample_rows())
    assert r.status_code == 200
    return client.post(f"/api/imports/{r.json()['sha256']}/commit")


def test_preview_then_commit(client, tmp_path):
    r = upload(client, tmp_path, sample_rows())
    body = r.json()
    assert body["committed"] is False and body["new"] == 5
    assert client.get("/api/transactions").json()["total"] == 0  # preview wrote nothing

    c = client.post(f"/api/imports/{body['sha256']}/commit")
    assert c.status_code == 200 and c.json()["new"] == 5
    assert client.get("/api/transactions").json()["total"] == 5
    assert client.post(f"/api/imports/{body['sha256']}/commit").status_code == 404  # staging is consumed


def test_direct_commit_and_history(client, tmp_path):
    body = upload(client, tmp_path, sample_rows(), dry_run=False).json()
    assert body["committed"] is True and body["new"] == 5
    history = client.get("/api/imports").json()
    assert len(history) == 1 and history[0]["n_new"] == 5


def test_second_upload_shows_only_the_difference(client, tmp_path):
    load(client, tmp_path)
    more = [row(7, "Food 🍕", "Coffee: new", 300)] + sample_rows()
    body = upload(client, tmp_path, more, name="next.xlsx").json()
    assert (body["new"], body["unchanged"], body["updated"], body["deleted"]) == (1, 5, 0, 0)


def test_bad_file_is_a_422(client, tmp_path):
    bad = tmp_path / "bad.xlsx"
    bad.write_text("nope")
    with open(bad, "rb") as fh:
        r = client.post("/api/imports", files={"file": ("bad.xlsx", fh)})
    assert r.status_code == 422 and "xlsx" in r.json()["detail"]


def test_unknown_commit_token(client):
    assert client.post("/api/imports/" + "0" * 64 + "/commit").status_code == 404
    assert client.post("/api/imports/not-a-hash/commit").status_code == 404


def test_transaction_filters(client, tmp_path):
    load(client, tmp_path)
    get = lambda **p: client.get("/api/transactions", params=p).json()  # noqa: E731
    assert get()["total"] == 5
    assert get(kind="income")["total"] == 1
    assert get(kind="transfer")["total"] == 1
    assert get(category="Food")["total"] == 2
    assert get(subcategory="coffee")["total"] == 1
    assert get(merchant="Blue Tokai")["total"] == 1
    assert get(q="petrol")["total"] == 1
    assert get(**{"from": "2026-03-04", "to": "2026-03-05"})["total"] == 2  # `to` is inclusive
    page = get(limit=2, offset=1)
    assert page["total"] == 5 and len(page["items"]) == 2
    newest = get(limit=1)["items"][0]
    assert newest["merchant"] == "blue tokai" and newest["category"] == "Food"


def test_deleted_rows_hidden_unless_asked(client, tmp_path):
    load(client, tmp_path)
    upload(client, tmp_path, [r for r in sample_rows() if r["category"] != "Garage"], name="b.xlsx", dry_run=False)
    assert client.get("/api/transactions").json()["total"] == 4
    assert client.get("/api/transactions", params={"include_deleted": True}).json()["total"] == 5


def test_summary_excludes_transfers_and_income_by_default(client, tmp_path):
    load(client, tmp_path)
    s = client.get("/api/summary", params={"group_by": "category"}).json()
    assert s["total"] == 2530 and s["count"] == 3
    assert {r["key"]: r["total"] for r in s["rows"]} == {"Garage": 2000, "Food": 530}
    assert client.get("/api/summary", params={"kind": "income"}).json()["total"] == 198000
    assert client.get("/api/summary", params={"kind": "transfer"}).json()["total"] == 40000


def test_summary_by_month_and_subcategory(client, tmp_path):
    rows = sample_rows() + [row(40, "Food 🍕", "Coffee: x", 100)]  # April
    load(client, tmp_path, rows)
    months = client.get("/api/summary", params={"group_by": "month"}).json()["rows"]
    assert [m["key"] for m in months] == ["2026-03", "2026-04"]
    sub = client.get("/api/summary", params={"group_by": "subcategory"}).json()["rows"]
    assert {r["key"]: r["total"] for r in sub}["coffee"] == 380
    assert any(r["key"] == "(none)" for r in sub)


def test_category_map_patch_reapplies_to_stored_rows(client, tmp_path):
    load(client, tmp_path)
    cm = {c["raw_category"]: c for c in client.get("/api/category-map").json()}
    assert cm["Investments"]["kind"] == "transfer" and cm["Garage"]["kind"] is None

    # Treat Garage as a transfer: it leaves the spend total.
    r = client.patch("/api/category-map/Garage", json={"kind": "transfer"})
    assert r.status_code == 200 and r.json()["kind"] == "transfer"
    assert client.get("/api/summary").json()["total"] == 530

    # Clearing the override falls back to each row's own direction.
    client.patch("/api/category-map/Garage", json={"kind": ""})
    assert client.get("/api/summary").json()["total"] == 2530

    # Renaming updates stored rows too, emoji-bearing key included.
    r = client.patch("/api/category-map/Food 🍕", json={"category": "Eating"})
    assert r.status_code == 200
    assert client.get("/api/transactions", params={"category": "Eating"}).json()["total"] == 2


def test_category_map_patch_validation(client, tmp_path):
    load(client, tmp_path)
    assert client.patch("/api/category-map/Nope", json={"kind": "income"}).status_code == 404
    assert client.patch("/api/category-map/Garage", json={"kind": "bogus"}).status_code == 422
    assert client.patch("/api/category-map/Garage", json={"category": "  "}).status_code == 422


def test_category_survives_reimport(client, tmp_path):
    load(client, tmp_path)
    client.patch("/api/category-map/Garage", json={"kind": "transfer"})
    upload(client, tmp_path, [row(6, "Garage", "Petrol", 100)] + sample_rows(), name="n.xlsx", dry_run=False)
    assert client.get("/api/summary").json()["total"] == 530  # new Garage row also follows the override
