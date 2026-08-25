function formatShort(ts) {
  const m = Math.floor(ts / 60);
  const s = (ts % 60).toFixed(1).padStart(4, "0");
  return `${m}:${s}`;
}

export default function Timeline({ id, dialogues, duration, activeIndex, onSelect }) {
  if (!dialogues.length || !duration) return null;

  return (
    <div id={id} className="bg-base-900 border border-base-700 rounded-lg p-5">
      <div className="flex items-center justify-between mb-3">
        <h3 className="section-marker font-mono text-xs uppercase tracking-widest text-neutral-500">
          02 · Timeline
        </h3>
        <span className="font-mono text-xs text-neutral-600">
          {formatShort(duration)} total
        </span>
      </div>

      <div className="relative h-10">
        <div className="absolute left-0 right-0 top-1/2 -translate-y-1/2 h-px bg-base-600" />
        {dialogues.map((d) => {
          const pct = Math.min(100, Math.max(0, (d.timestamp_sec / duration) * 100));
          const active = d.index === activeIndex;
          return (
            <button
              key={d.index}
              type="button"
              onClick={() => onSelect(d.index)}
              title={`${formatShort(d.timestamp_sec)} — ${d.text}`}
              style={{ left: `${pct}%` }}
              className={`group absolute top-1/2 -translate-x-1/2 -translate-y-1/2 w-2.5 h-2.5 rounded-full border transition-all ${
                active
                  ? "bg-amber-500 border-amber-400 scale-125"
                  : "bg-base-700 border-base-600 hover:bg-amber-500/70 hover:border-amber-500"
              }`}
            >
              <span className="pointer-events-none absolute bottom-full mb-2 left-1/2 -translate-x-1/2 whitespace-nowrap font-mono text-xs bg-base-800 border border-base-600 rounded px-1.5 py-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
                {formatShort(d.timestamp_sec)}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}