function formatTs(ts) {
  const h = Math.floor(ts / 3600);
  const m = Math.floor((ts % 3600) / 60);
  const s = (ts % 60).toFixed(2).padStart(5, "0");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s}`;
}

export default function DialogueCard({ dialogue, active, onOpenFrame }) {
  return (
    <li
      id={`dialogue-${dialogue.index}`}
      className={`flex gap-4 rounded-lg border p-3 transition-colors ${
        active
          ? "border-amber-500/60 bg-amber-500/5"
          : "border-base-700 bg-base-900 hover:border-base-600"
      }`}
    >
      <button
        type="button"
        onClick={() => onOpenFrame(dialogue)}
        className="shrink-0 w-28 h-20 rounded overflow-hidden bg-base-800 border border-base-700 flex items-center justify-center"
      >
        {dialogue.frame_url ? (
          <img
            src={dialogue.frame_url}
            alt={`Frame at ${formatTs(dialogue.timestamp_sec)}`}
            className="w-full h-full object-cover"
          />
        ) : (
          <span className="text-neutral-700 text-xs font-mono">no frame</span>
        )}
      </button>

      <div className="min-w-0 flex-1">
        <p className="text-sm text-neutral-100 leading-snug break-words">
          {dialogue.text}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-neutral-500">
          <span className="text-amber-500">{formatTs(dialogue.timestamp_sec)}</span>
          <span>frame {dialogue.frame_number}</span>
          {typeof dialogue.confidence === "number" && (
            <span>conf {(dialogue.confidence * 100).toFixed(0)}%</span>
          )}
          {typeof dialogue.relevance === "number" && (
            <span className="text-neutral-600">
              match {(dialogue.relevance * 100).toFixed(0)}%
            </span>
          )}
        </div>
      </div>
    </li>
  );
}
