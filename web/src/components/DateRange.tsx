import { Preset, PRESETS } from "../format";

type Props = {
  preset: Preset | "custom";
  from: string;
  to: string;
  onPreset: (id: Preset) => void;
  onFrom: (value: string) => void;
  onTo: (value: string) => void;
};

/** Preset buttons plus custom From/To dates. Shared by Overview and Transactions. */
export default function DateRange({ preset, from, to, onPreset, onFrom, onTo }: Props) {
  return (
    <div className="presets" role="group" aria-label="Date range">
      {PRESETS.map((p) => (
        <button type="button" key={p.id} className="preset" aria-pressed={preset === p.id} onClick={() => onPreset(p.id)}>
          {p.label}
        </button>
      ))}
      <label className="field">
        From
        <input type="date" value={from} onChange={(e) => onFrom(e.target.value)} />
      </label>
      <label className="field">
        To
        <input type="date" value={to} onChange={(e) => onTo(e.target.value)} />
      </label>
    </div>
  );
}
