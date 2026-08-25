const LABELS = {
  pending: "Queued",
  processing: "Scanning video for on-screen text…",
  done: "Done",
  error: "Failed",
};

export default function StatusBanner({ status, error }) {
  if (!status) return null;

  if (status === "error") {
    return (
      <div className="border border-miss/40 bg-miss/10 rounded-lg px-4 py-3 flex items-center gap-3">
        <span className="w-2 h-2 rounded-full bg-miss shrink-0" />
        <p className="text-sm text-neutral-200">
          <span className="font-medium text-miss">{LABELS.error}.</span>{" "}
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
          <span className="font-medium text-found">{LABELS.done}.</span>{" "}
          Every detected line is listed below.
        </p>
      </div>
    );
  }

  return (
    <div className="relative overflow-hidden border border-amber-600/40 bg-base-900 rounded-lg px-4 py-3 flex items-center gap-3">
      <div className="absolute inset-0 film-scan animate-pulse opacity-60" aria-hidden="true" />
      <span className="relative w-2 h-2 rounded-full bg-amber-500 animate-pulse shrink-0" />
      <p className="relative text-sm text-neutral-200 font-mono">
        {LABELS[status] || status}
      </p>
    </div>
  );
}
