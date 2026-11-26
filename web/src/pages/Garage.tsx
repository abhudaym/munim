import { useEffect, useState } from "react";
import { GarageData, insights } from "../api";
import { TimeChart } from "../components/Chart";
import { fmtDay, inr, monthLabel, num } from "../format";
import { isHidden } from "../privacy";

const SHADES = ["#ffb000", "#c98a00", "#8a6410", "#56605a", "#3a423d", "#2a312c"];
const perKm = (v: number | null) => (v === null ? "–" : isHidden() ? "₹****" : `₹${v.toFixed(2)}`);

export default function Garage() {
  const [data, setData] = useState<GarageData | null>(null);
  const [error, setError] = useState("");
  const [trip, setTrip] = useState("20");
  const [fare, setFare] = useState("");

  useEffect(() => {
    insights.garage().then(setData).catch((e: Error) => setError(e.message));
  }, []);
  if (error) return <div className="banner error">Could not load the car: {error}</div>;
  if (!data) return <p className="muted">Loading…</p>;

  const km = Number(trip) || 0;
  const cab = fare === "" ? null : Number(fare);
  const petrol = data.petrol_per_km === null ? null : Math.round(km * data.petrol_per_km);
  const allIn = data.per_km === null ? null : Math.round(km * data.per_km);
  const latest = data.months[data.months.length - 1];

  return (
    <>
      <h1>
        Garage <span className="muted">/ from your {data.category} entries and odometer notes</span>
      </h1>

      <section className="garage-top">
        <div className="card car-slot">
          <div className="tile-label">The car</div>
          <div className="car-model" aria-hidden="true">
            <svg width="170" height="74" viewBox="0 0 160 70" fill="none" stroke="var(--accent)" strokeWidth="2">
              <path d="M8 50h144M20 50l6-16 22-14h52l26 14 18 4v12" />
              <circle cx="44" cy="52" r="10" fill="var(--card)" />
              <circle cx="118" cy="52" r="10" fill="var(--card)" />
              <path d="M52 22l-6 12h40V22M92 22v12h26" />
            </svg>
            <span className="muted">3D model coming later</span>
          </div>
          {data.odometer_km !== null ? (
            <>
              <div>
                odometer <b className="mono">{num(data.odometer_km)} km</b>
              </div>
              <div className="tile-note">
                last reading {fmtDay(data.odometer_on!)}
                {data.km_since_service !== null && ` · ${num(data.km_since_service)} km since the last service`}
              </div>
            </>
          ) : (
            <div className="tile-note">No odometer readings yet. Type the reading, like "15983 kms", in a petrol entry's description.</div>
          )}
        </div>
        <div className="tiles garage-tiles">
          <div className="card">
            <div className="tile-label">All-in cost / km</div>
            <div className="tile-value">{perKm(data.per_km)}</div>
            <div className="tile-note">everything in {data.category}, last 6 months. EMI not included</div>
          </div>
          <div className="card">
            <div className="tile-label">Petrol / km</div>
            <div className="tile-value">{perKm(data.petrol_per_km)}</div>
            <div className="tile-note">what one more trip costs</div>
          </div>
          <div className="card">
            <div className="tile-label">Km in {monthLabel(latest.month)}</div>
            <div className="tile-value">{latest.km === null ? "–" : num(Math.round(latest.km))}</div>
            <div className="tile-note">
              {data.km_avg === null ? "needs readings" : `average ${num(Math.round(data.km_avg))} a month`} · spent {inr(Math.round(data.spent_month))}
            </div>
          </div>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Km per month</h2>
          <TimeChart points={data.months.map((m) => ({ label: m.month, value: Math.round(m.km ?? 0) }))} column="km" line={false} />
        </div>
        <div className="card">
          <h2>All-in ₹ per km, by month</h2>
          <TimeChart points={data.months.map((m) => ({ label: m.month, value: m.per_km ?? 0 }))} column="cost_per_km" line={false} />
          <div className="tile-note">A month with a service or a big purchase stands out here.</div>
        </div>
      </section>

      <section className="grid">
        <div className="card">
          <h2>Where the money goes</h2>
          <div className="split" aria-hidden="true">
            {data.buckets.map((b, i) => (
              <span key={b.name} style={{ width: `${b.share * 100}%`, background: SHADES[i % SHADES.length] }} />
            ))}
          </div>
          {data.buckets.map((b, i) => (
            <div className="split-row" key={b.name}>
              <span className="swatch" style={{ background: SHADES[i % SHADES.length] }} />
              <span>{b.name}</span>
              <span className="muted right">{isHidden() ? "****" : `${Math.round(b.share * 100)}%`}</span>
              <span className="mono right">{inr(Math.round(b.monthly))}</span>
            </div>
          ))}
          <div className="tile-note">average a month, last 6 months</div>
        </div>

        <div className="card">
          <h2>Service log</h2>
          {data.services.length === 0 && <div className="muted">No service, oil, tyre or insurance entries yet.</div>}
          {data.services.map((s) => (
            <div className="svc-row" key={`${s.day}${s.what}`}>
              <div>
                <div>{s.what}</div>
                <div className="muted">
                  {fmtDay(s.day)}
                  {s.odometer_km !== null && ` · ${num(s.odometer_km)} km`}
                </div>
              </div>
              <span className="mono right">{inr(s.amount)}</span>
            </div>
          ))}
          <div className="tile-note">Odometer at a service is estimated from the readings either side.</div>
        </div>

        <div className="card">
          <h2>Car or cab?</h2>
          <label className="field">
            <span className="muted">Trip distance, km</span>
            <input inputMode="decimal" value={trip} onChange={(e) => setTrip(e.target.value)} />
          </label>
          <label className="field">
            <span className="muted">Cab fare you were quoted, ₹ (optional)</span>
            <input inputMode="decimal" value={fare} onChange={(e) => setFare(e.target.value)} />
          </label>
          <div className="kv" style={{ gridTemplateColumns: "1fr auto", marginTop: 12 }}>
            <span>Car, petrol only</span>
            <b className="mono">{petrol === null ? "–" : inr(petrol)}</b>
            <span>Car, all-in</span>
            <b className="mono">{allIn === null ? "–" : inr(allIn)}</b>
            {cab !== null && (
              <>
                <span>Cab</span>
                <b className="mono">{inr(cab)}</b>
              </>
            )}
          </div>
          {cab !== null && petrol !== null && allIn !== null && (
            <p style={{ color: cab > allIn ? "var(--good)" : cab < petrol ? "var(--bad)" : undefined }}>
              {cab > allIn
                ? `The car is cheaper even counting everything, by ${inr(cab - allIn)}.`
                : cab < petrol
                  ? `The cab is cheaper even than the petrol, by ${inr(petrol - cab)}.`
                  : `The car is cheaper on petrol alone, but not once service and the rest are counted.`}
            </p>
          )}
          <div className="tile-note">Parking and tolls for this trip aren't included. Add them to the car side if you know them.</div>
        </div>
      </section>
      {data.readings < 2 && <div className="banner">Cost per km needs at least two odometer readings.</div>}
    </>
  );
}
