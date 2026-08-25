function formatTs(ts) {
  const h = Math.floor(ts / 3600);
  const m = Math.floor((ts % 3600) / 60);
  const s = (ts % 60).toFixed(2).padStart(5, "0");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s}`;
}

export default function TargetMatchCard({ match, onOpenFrame }) {
  if (!match) return null;

  if (!match.matched) {
    return (
      <div className="border border-miss/40 bg-miss/5 rounded-lg p-5">
        <p className="font-mono text-xs uppercase tracking-widest text-miss mb-1.5">
          No confident match
        </p>
        <p className="text-sm text-neutral-300">
          "{match.target_text}" didn't clear the similarity threshold anywhere
          in this video.
        </p>
      </div>
    );
  }

  return (
    <div className="border border-found/50 bg-found/5 rounded-lg p-5 flex flex-col md:flex-row gap-5">
      <button
        type="button"
        onClick={() => onOpenFrame(match)}
        className="shrink-0 w-full md:w-56 h-36 rounded-md overflow-hidden bg-base-800 border border-base-700"
      >
        {match.frame_url ? (
          <img
            src={match.frame_url}
            alt={`First frame of "${match.target_text}"`}
            className="w-full h-full object-cover"
          />
        ) : (
          <div className="w-full h-full flex items-center justify-center text-neutral-700 text-xs font-mono">
            no frame
          </div>
        )}
      </button>

      <div className="min-w-0 flex-1">
        <p className="font-mono text-xs uppercase tracking-widest text-found mb-1.5">
          First appearance found
        </p>
        <p className="text-lg text-neutral-50 font-medium leading-snug mb-3">
          "{match.target_text}"
        </p>
        <dl className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div>
            <dt className="text-neutral-600">Timestamp</dt>
            <dd className="text-amber-400 mt-0.5">{formatTs(match.timestamp_sec)}</dd>
          </div>
          <div>
            <dt className="text-neutral-600">Frame</dt>
            <dd className="text-neutral-200 mt-0.5">{match.frame_number}</dd>
          </div>
          <div>
            <dt className="text-neutral-600">Similarity</dt>
            <dd className="text-neutral-200 mt-0.5">
              {(match.similarity * 100).toFixed(0)}%
            </dd>
          </div>
          <div>
            <dt className="text-neutral-600">OCR confidence</dt>
            <dd className="text-neutral-200 mt-0.5">
              {(match.ocr_confidence * 100).toFixed(0)}%
            </dd>
          </div>
        </dl>
      </div>
    </div>
  );
}
