"""The car: distance from odometer readings, cost per km, where the money goes, and services."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time

from munim.insights.data import Txn, add_months, month_key

CATEGORY = "Garage"
MONTHS = 6
BUCKETS = (  # first match wins
    ("Petrol", re.compile(r"petrol|diesel|fuel|cng")),
    ("Service", re.compile(r"service|oil|tyre|tire|puncture|battery|repair|brake|alignment")),
    ("Parking & tolls", re.compile(r"parking|toll|fastag")),
    ("Wash", re.compile(r"wash|clean|detailing")),
    ("Insurance", re.compile(r"insurance")),
)
SERVICE_LOG = re.compile(r"service|oil change|tyre|tire|insurance|battery")


@dataclass
class GarageMonth:
    month: str
    km: float | None  # None when the month is not covered by readings on both sides
    cost: float
    petrol: float
    per_km: float | None


@dataclass
class Bucket:
    name: str
    monthly: float
    share: float


@dataclass
class ServiceEntry:
    day: date
    what: str
    amount: float
    odometer_km: int | None


@dataclass
class Garage:
    category: str
    readings: int
    odometer_km: int | None
    odometer_on: date | None
    per_km: float | None  # all Garage spend over the covered months / km
    petrol_per_km: float | None
    km_month: float | None  # the latest covered month
    km_avg: float | None
    spent_month: float  # Garage spend in the as-of month
    months: list[GarageMonth]
    buckets: list[Bucket]
    services: list[ServiceEntry]
    km_since_service: int | None


def _interp(readings: list[tuple[datetime, int]], at: datetime) -> float | None:
    """Odometer at a moment, by straight line between the readings either side. None outside them."""
    if not readings or at < readings[0][0] or at > readings[-1][0]:
        return None
    for (t0, k0), (t1, k1) in zip(readings, readings[1:]):
        if t0 <= at <= t1:
            span = (t1 - t0).total_seconds()
            return k0 if span == 0 else k0 + (k1 - k0) * (at - t0).total_seconds() / span
    return float(readings[-1][1])


def bucket(merchant: str) -> str:
    for name, rx in BUCKETS:
        if rx.search(merchant):
            return name
    return "Other"


def garage(txns: list[Txn], today: date) -> Garage:
    car = [t for t in txns if t.kind == "expense" and t.category == CATEGORY and t.day <= today]
    readings: list[tuple[datetime, int]] = []
    for t in sorted((t for t in txns if t.odometer_km and t.day <= today), key=lambda t: t.ts):
        if not readings or t.odometer_km >= readings[-1][1]:  # ignore a reading that goes backwards
            readings.append((t.ts, t.odometer_km))

    this_month = date(today.year, today.month, 1)
    months: list[GarageMonth] = []
    for i in range(MONTHS - 1, -1, -1):
        m = add_months(this_month, -i)
        nxt = add_months(m, 1)
        a = _interp(readings, datetime.combine(m, time.min))
        end = datetime.combine(nxt, time.min)
        if m == this_month and readings:  # so far: up to the latest reading this month
            end = min(end, readings[-1][0])
        b = _interp(readings, end)
        km = round(b - a, 1) if a is not None and b is not None and b > a else None
        ts = [t for t in car if m <= t.day < nxt]
        cost = sum(t.amount for t in ts)
        petrol = sum(t.amount for t in ts if bucket(t.merchant) == "Petrol")
        months.append(GarageMonth(month_key(m), km, round(cost, 2), round(petrol, 2),
                                  round(cost / km, 2) if km else None))

    covered = [g for g in months if g.km]
    km_total = sum(g.km for g in covered)
    per_km = round(sum(g.cost for g in covered) / km_total, 2) if km_total else None
    petrol_per_km = round(sum(g.petrol for g in covered) / km_total, 2) if km_total else None

    window = [t for t in car if t.day >= add_months(this_month, -(MONTHS - 1))]
    n_months = MONTHS
    totals: dict[str, float] = {}
    for t in window:
        b = bucket(t.merchant)
        totals[b] = totals.get(b, 0) + t.amount
    whole = sum(totals.values())
    buckets = sorted(
        (Bucket(k, round(v / n_months, 2), round(v / whole, 4)) for k, v in totals.items()),
        key=lambda b: -b.monthly,
    )

    services = []
    for t in reversed(car):
        if SERVICE_LOG.search(t.merchant):
            odo = t.odometer_km or _interp(readings, t.ts)
            services.append(ServiceEntry(t.day, t.merchant, round(t.amount, 2), None if odo is None else round(odo)))
    last_odo = readings[-1][1] if readings else None
    since = None
    svc_with_odo = [s for s in services if s.odometer_km is not None and "insurance" not in s.what]
    if svc_with_odo and last_odo is not None:
        since = last_odo - svc_with_odo[0].odometer_km

    return Garage(
        category=CATEGORY, readings=len(readings),
        odometer_km=last_odo, odometer_on=readings[-1][0].date() if readings else None,
        per_km=per_km, petrol_per_km=petrol_per_km,
        km_month=covered[-1].km if covered else None,
        km_avg=round(km_total / len(covered), 1) if covered else None,
        spent_month=months[-1].cost if months else 0.0,
        months=months, buckets=buckets, services=services[:10], km_since_service=since,
    )
