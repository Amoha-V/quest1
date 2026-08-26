const STAGES = [
  { id: "download", label: "Download video" },
  { id: "probe", label: "Read metadata" },
  { id: "scan", label: "Scan for dialogue" },
  { id: "refine", label: "Pin exact first frame" },
  { id: "save", label: "Save results" },
];

const STAGE_ORDER = {
  queued: -1,
  download: 0,
  probe: 1,
  scan: 2,
  refine: 3,
  save: 4,
  done: 5,
  error: -1,
};

function stageIndex(stage) {
  if (!stage) return -1;
  if (stage in STAGE_ORDER) return STAGE_ORDER[stage];
  return STAGES.findIndex((s) => s.id === stage);
}

export default function StatusBanner({ status, error, stage, message, progress, cached }) {
  if (!status) return null;

  if (status === "error") {
    return (
      <div className="border border-miss/40 bg-miss/10 rounded-lg px-4 py-3 flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-miss shrink-0" />
        <p className="text-sm text-neutral-200">
          <span className="font-medium text-miss">Failed.</span>{" "}
          {error || "Something went wrong while processing this video."}
        </p>
      </div>
    );
  }

  if (status === "done") {
    return (
      <div className="border border-found/40 bg-found/10 rounded-lg px-4 py-3 flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-found shrink-0" />
        <p className="text-sm text-neutral-200">
          {cached ? (
            <>
              <span className="font-medium text-found">Cache hit.</span>{" "}
              Same video and dialogue were already processed — result loaded without re-running OCR.
            </>
          ) : (
            <>
              <span className="font-medium text-found">Done.</span>{" "}
              First dialogue appearance is ready below.
            </>
          )}
        </p>
      </div>
    );
  }

  const current = stageIndex(stage);
  const pct =
    typeof progress === "number" && !Number.isNaN(progress)
      ? Math.max(0, Math.min(100, Math.round(progress * 100)))
      : null;

  return (
    <div className="relative overflow-hidden border border-amber-600/40 bg-base-900 rounded-lg px-4 py-4 space-y-3">
      <div className="absolute inset-0 film-scan animate-pulse opacity-40" aria-hidden="true" />

      <div className="relative flex items-start gap-3">
        <span className="mt-1.5 w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-neutral-200 font-mono">
            {message || (status === "pending" ? "Queued…" : "Processing…")}
          </p>
          {pct !== null && (
            <div className="mt-2 h-1.5 w-full bg-base-800 rounded overflow-hidden">
              <div
                className="h-full bg-amber-500 transition-[width] duration-500 ease-out"
                style={{ width: `${pct}%` }}
              />
            </div>
          )}
          {pct !== null && (
            <p className="mt-1 font-mono text-[10px] uppercase tracking-widest text-neutral-600">
              {pct}%
            </p>
          )}
        </div>
      </div>

      <ol className="relative grid grid-cols-1 sm:grid-cols-5 gap-2">
        {STAGES.map((s, i) => {
          const done = current > i || status === "done";
          const active = current === i && status === "processing";
          return (
            <li
              key={s.id}
              className={[
                "rounded-md border px-2.5 py-2 font-mono text-[11px] leading-snug",
                done
                  ? "border-found/30 bg-found/5 text-found"
                  : active
                    ? "border-amber-500/50 bg-amber-500/10 text-amber-300"
                    : "border-base-700 bg-base-950/40 text-neutral-600",
              ].join(" ")}
            >
              <span className="block text-[9px] uppercase tracking-widest opacity-70 mb-0.5">
                {String(i + 1).padStart(2, "0")}
              </span>
              {s.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}
