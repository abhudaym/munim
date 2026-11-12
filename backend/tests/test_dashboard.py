from datetime import date

import pytest
from fastapi.testclient import TestClient

from munim.api.app import create_app
from munim.ask import Draft, QueryError, connect_readonly, run_query
from munim.ask.charts import choose_chart
from munim.ask.context import date_tokens
from munim.ask.dashboard import is_rolling, render, to_template
from tests.helpers import FakeLLM

TODAY = date(2026, 4, 10)
COFFEE = "SELECT sum(amount) AS spent FROM v_expenses WHERE subcategory = 'coffee'"
BY_MONTH = "SELECT month, sum(amount) AS spent FROM v_expenses GROUP BY month ORDER BY month"
BY_TAG = "SELECT subcategory, sum(amount) AS spent FROM v_expenses WHERE subcategory IS NOT NULL GROUP BY 1 ORDER BY 2 DESC"


# ---------------------------------------------------------------- chart choice

@pytest.mark.parametrize(
    "columns,rows,chart,charts",
    [
        (["spent"], [[1440.0]], "number", ["number", "table"]),
        (["name"], [["blue tokai"]], "table", ["table"]),
        (["month", "spent"], [["2026-02", 550.0], ["2026-03", 4050.0]], "bars", ["bars", "line", "table"]),
        (["txn_date", "spent"], [["2026-02-01", 5.0], ["2026-02-02", 7.0]], "bars", ["bars", "line", "table"]),
        (["category", "spent"], [["Food", 9.0], ["Garage", 4.0]], "bars", ["bars", "table"]),
        (["category", "spent"], [[f"c{i}", float(i)] for i in range(13)], "table", ["table", "bars"]),
        (["category", "spent"], [[f"c{i}", float(i)] for i in range(31)], "table", ["table"]),
        (["category", "spent"], [["Food", 9.0]], "table", ["table"]),
        (["a", "b"], [["x", "y"], ["z", "w"]], "table", ["table"]),
        (["category", "net"], [["Food", -9.0], ["Garage", 4.0]], "table", ["table"]),
        (["txn_date", "note", "amount"], [["2026-02-01", "Petrol", 5.0], ["2026-02-02", "Shoes", 7.0]], "table", ["table"]),
        (["txn_date", "amount"], [["2026-02-01", 5.0], ["2026-02-01", 7.0]], "table", ["table"]),
        ([], [], "table", ["table"]),
        (["spent"], [], "table", ["table"]),
    ],
)
def test_chart_follows_the_shape(columns, rows, chart, charts):
    choice = choose_chart(columns, rows)
    assert (choice.chart, choice.charts) == (chart, charts)


def test_value_column_prefers_money_over_counts():
    choice = choose_chart(["month", "n", "spent"], [["2026-02", 2, 550.0], ["2026-03", 5, 4050.0]])
    assert choice.value_col == 2 and choice.time is True
    assert choose_chart(["tag", "n"], [["coffee", 5], ["eatout", 2]]).value_col == 1


# ---------------------------------------------------------------- rolling dates

def test_known_dates_become_placeholders_and_move_with_today():
    t = date_tokens(TODAY)
    sql = f"SELECT sum(amount) FROM v_expenses WHERE txn_date >= '{t['three_months_ago']}' AND txn_date <= '{t['today']}'"
    template = to_template(sql, TODAY)
    assert "'{three_months_ago}'" in template and "'{today}'" in template and is_rolling(template)
    assert render(template, TODAY) == sql
    later = render(template, date(2026, 6, 30))
    assert "'2026-03-30'" in later and "'2026-06-30'" in later


def test_other_dates_and_text_are_left_alone():
    sql = "SELECT 1 FROM v_expenses WHERE txn_date >= '2025-07-04' AND note = '{today}'"
    template = to_template(sql, TODAY)
    assert template == sql and not is_rolling("SELECT 1 FROM v_expenses WHERE txn_date >= '2025-07-04'")


def test_shared_start_dates_pick_the_narrower_window():
    jan = date(2026, 1, 20)
    assert "'{month_start}'" in to_template("SELECT 1 FROM v_expenses WHERE txn_date >= '2026-01-01'", jan)


def test_tiles_table_is_not_readable_by_questions(db_path):
    conn = connect_readonly(db_path)
    try:
        with pytest.raises(QueryError):
            run_query(conn, "SELECT * FROM dashboard_tiles")
    finally:
        conn.close()


# ---------------------------------------------------------------- api

@pytest.fixture()
def api(db_path, data_dir):
    with TestClient(create_app(data_dir, llm=FakeLLM(Draft(BY_MONTH, "by month")), load_llm_from_env=False)) as c:
        yield c


def pin(api, sql=COFFEE, title="Coffee", **extra):
    return api.post("/api/dashboard/tiles", json={"title": title, "question": "q?", "sql": sql, **extra})


def test_ask_suggests_a_chart(api):
    body = api.post("/api/ask", json={"question": "spend per month"}).json()
    assert body["chart"] == "bars" and body["charts"] == ["bars", "line", "table"]
    assert body["value_col"] == 1 and body["time"] is True and body["rolling"] is False


def test_pin_then_dashboard_runs_it_fresh(api):
    r = pin(api)
    assert r.status_code == 201
    tile = r.json()
    assert tile["chart"] == "number" and tile["rows"] == [[1440.0]] and tile["rolling"] is False
    (shown,) = api.get("/api/dashboard").json()
    assert shown["id"] == tile["id"] and shown["rows"] == [[1440.0]] and shown["error"] is None


def test_tile_follows_the_data_without_a_model(api, tmp_path):
    from tests.helpers import ask_rows, make_xlsx, row

    pin(api)
    rows = [r for r in ask_rows() if not (r["note"] == "Petrol" and r["amount"] == 2100)]
    rows.insert(0, row(34, "Food 🍕", "Coffee: subko", 360))
    path = make_xlsx(tmp_path / "c.xlsx", rows)
    with open(path, "rb") as fh:
        assert api.post("/api/imports?dry_run=false", files={"file": ("c.xlsx", fh)}).status_code == 200
    assert api.get("/api/dashboard").json()[0]["rows"] == [[1800.0]]


def test_rolling_pin_stores_placeholders(api, session):
    from munim.db import DashboardTile

    start = date_tokens(date.today())["year_start"]
    sql = f"SELECT count(*) AS n FROM v_expenses WHERE txn_date >= '{start}'"
    tile = pin(api, sql=sql).json()
    assert tile["rolling"] is True and tile["sql"] == sql  # shown with today's dates filled in
    assert "{year_start}" in session.get(DashboardTile, tile["id"]).sql

    fixed = pin(api, sql=sql, rolling=False).json()
    assert fixed["rolling"] is False and session.get(DashboardTile, fixed["id"]).sql == sql


def test_chart_choice_is_kept_or_corrected(api):
    assert pin(api, sql=BY_MONTH, chart="line").json()["chart"] == "line"
    assert pin(api, sql=BY_TAG, chart="line").json()["chart"] == "bars"  # a line needs dates
    assert pin(api, sql=BY_TAG).json()["chart"] == "bars"


@pytest.mark.parametrize("sql", ["DROP TABLE transactions", "SELECT * FROM transactions", "SELECT nope FROM v_expenses"])
def test_unsafe_or_broken_queries_cannot_be_pinned(api, sql):
    assert pin(api, sql=sql).status_code == 422
    assert api.get("/api/dashboard").json() == []


def test_rename_switch_chart_move_and_delete(api):
    a, b, c = (pin(api, title=t).json()["id"] for t in "abc")
    assert api.patch(f"/api/dashboard/tiles/{a}", json={"title": "Coffee, ever", "chart": "table"}).json()["chart"] == "table"
    api.patch(f"/api/dashboard/tiles/{c}", json={"move": -1})
    api.patch(f"/api/dashboard/tiles/{a}", json={"move": -1})  # already first: stays put
    assert [t["id"] for t in api.get("/api/dashboard").json()] == [a, c, b]
    assert api.delete(f"/api/dashboard/tiles/{c}").status_code == 204
    assert [t["title"] for t in api.get("/api/dashboard").json()] == ["Coffee, ever", "b"]
    assert api.delete(f"/api/dashboard/tiles/{c}").status_code == 404
    assert api.patch("/api/dashboard/tiles/999", json={"title": "x"}).status_code == 404


def test_a_tile_that_breaks_later_reports_instead_of_failing_the_page(api, session):
    from munim.db import DashboardTile

    tile = pin(api).json()
    session.get(DashboardTile, tile["id"]).sql = "SELECT * FROM transactions"
    session.commit()
    pin(api, title="still fine")
    first, second = api.get("/api/dashboard").json()
    assert first["error"] and first["rows"] == [] and second["rows"] == [[1440.0]]
