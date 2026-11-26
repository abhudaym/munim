from datetime import date, datetime, timedelta

from munim.insights.data import Txn, as_of
from munim.insights.garage import bucket, garage
from munim.insights.month import month_insight
from munim.insights.recurring import find_recurring, still_to_come
from munim.insights.trends import trends


def t(day, amount, category="Food", merchant="cafe", kind="expense", hour=12, minute=0, odo=None):
    d = date.fromisoformat(day)
    return Txn(datetime(d.year, d.month, d.day, hour, minute), kind, amount, category, merchant, odo)


def test_as_of_stops_at_the_last_entry():
    assert as_of([t("2026-09-28", 1)], date(2026, 11, 26)) == date(2026, 9, 28)
    assert as_of([], date(2026, 11, 26)) == date(2026, 11, 26)


def test_pace_compares_the_same_days_of_earlier_months():
    txns = []
    for m in range(3, 9):  # Mar..Aug: 1000 on the 5th, 3000 on the 25th
        txns += [t(f"2026-{m:02d}-05", 1000), t(f"2026-{m:02d}-25", 3000)]
    txns += [t("2026-09-05", 2500)]
    mi = month_insight(txns, date(2026, 9, 10))
    assert mi.spent == 2500 and mi.history_months == 6
    assert mi.usual_to_date == 1000  # only the 5th falls before day 10
    assert mi.usual_month == 4000
    assert mi.projected == 2500 + 3000


def test_movers_name_the_merchants_behind_the_change():
    txns = [t(f"2026-{m:02d}-03", 500, "Social Life", "pub") for m in range(3, 9)]
    txns += [t("2026-09-03", 500, "Social Life", "pub"), t("2026-09-04", 4000, "Social Life", "sector 56")]
    mi = month_insight(txns, date(2026, 9, 10))
    assert mi.movers[0].category == "Social Life"
    assert mi.movers[0].delta == 4000 and mi.movers[0].merchants == ["sector 56"]


def test_small_moves_are_not_listed():
    txns = [t(f"2026-{m:02d}-03", 500) for m in range(3, 10)] + [t("2026-09-04", 400)]
    assert month_insight(txns, date(2026, 9, 10)).movers == []


def test_flags_duplicates_and_unusually_big_charges():
    txns = [t(f"2026-0{m}-03", 300, merchant="blue tokai") for m in range(3, 9)]
    txns += [
        t("2026-09-22", 284, merchant="blue tokai", hour=10, minute=2),
        t("2026-09-22", 284, merchant="blue tokai", hour=10, minute=13),
        t("2026-09-23", 2400, merchant="blue tokai"),
    ]
    kinds = [f.kind for f in month_insight(txns, date(2026, 9, 30)).flags]
    assert kinds == ["duplicate", "big"]


def test_recurring_finds_a_monthly_charge_despite_a_doubled_entry():
    days = ["2026-01-24", "2026-01-29", "2026-03-30", "2026-04-28", "2026-05-28", "2026-06-29", "2026-07-28", "2026-08-29"]
    items = find_recurring([t(d, 149, "Subscriptions", "apple music") for d in days], date(2026, 9, 10))
    assert len(items) == 1
    r = items[0]
    assert r.every == "monthly" and r.next == date(2026, 9, 29) and not r.stopped
    assert still_to_come(items, date(2026, 9, 10)) == items


def test_recurring_notices_a_price_rise_and_a_stop():
    jio = [t(f"2026-0{m}-28", 299 if m < 7 else 349, "Bills", "jio") for m in range(2, 10)]
    netflix = [t(f"2026-0{m}-14", 649, "Subscriptions", "netflix") for m in range(2, 6)]
    items = {r.merchant: r for r in find_recurring(jio + netflix, date(2026, 9, 30))}
    assert items["jio"].previous_amount is None  # the rise was in July, not the latest charge
    assert items["netflix"].stopped and items["netflix"].next is None


def test_irregular_merchants_are_not_recurring():
    days = ["2026-02-06", "2026-03-16", "2026-04-18", "2026-05-31", "2026-08-19"]
    assert find_recurring([t(d, 473, "Apparel", "haircut") for d in days], date(2026, 9, 1)) == []


def test_transfers_count_as_recurring_and_emi_is_not_saved():
    txns = []
    for m in range(1, 10):
        txns += [
            t(f"2026-{m:02d}-01", 100000, "Salary", "salary", "income"),
            t(f"2026-{m:02d}-02", 20000, "EMI", "car emi", "transfer"),
            t(f"2026-{m:02d}-03", 30000, "Investments", "sip", "transfer"),
            t(f"2026-{m:02d}-10", 40000),
        ]
    assert {"car emi", "sip"} <= {r.merchant for r in find_recurring(txns, date(2026, 9, 20))}
    tr = trends(txns, date(2026, 10, 5))
    assert tr.savings[-1].rate == 0.4  # (100k - 40k spend - 20k EMI) / 100k; the SIP counts as saved


def test_growth_needs_enough_history_and_marks_faster_than_income():
    txns = []
    for m in range(1, 9):
        txns += [t(f"2026-{m:02d}-01", 100000, "Salary", "salary", "income"), t(f"2026-{m:02d}-05", 2000 if m <= 4 else 5000, "Social Life", "pub")]
    g = {x.category: x for x in trends(txns, date(2026, 9, 1)).growth}
    assert g["Income"].pct == 0 and g["Social Life"].pct == 1.5 and g["Social Life"].faster_than_income
    assert trends(txns[:8], date(2026, 5, 1)).growth == []  # only 4 months: 2 vs 2 is too little


def test_when_you_spend_grid():
    txns = [t("2026-08-01", 300, hour=23), t("2026-08-03", 100, hour=9)]  # Sat late night, Mon morning
    tr = trends(txns, date(2026, 9, 1))
    assert tr.grid[5][3] == 300 and tr.grid[0][0] == 100
    assert tr.weekend_share == 0.75 and tr.top_slot == "Sat late night"


def test_garage_cost_per_km_from_interpolated_readings():
    txns = [
        t("2026-07-01", 3000, "Garage", "petrol", odo=10000),
        t("2026-08-01", 3000, "Garage", "petrol", odo=11000),
        t("2026-08-15", 2000, "Garage", "service 2"),
        t("2026-09-01", 3000, "Garage", "petrol", odo=12000),
    ]
    g = garage(txns, date(2026, 9, 1))
    aug = next(m for m in g.months if m.month == "2026-08")
    assert round(aug.km) == 1000 and aug.cost == 5000 and aug.per_km == 5.0
    assert g.odometer_km == 12000 and g.services[0].what == "service 2"
    assert g.services[0].odometer_km == round(11000 + 1000 * 14 / 31)
    assert bucket("toll annual pass") == "Parking & tolls" and bucket("dashcam") == "Other"
