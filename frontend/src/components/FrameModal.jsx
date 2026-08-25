import { useEffect } from "react";

function formatTs(ts) {
  const h = Math.floor(ts / 3600);
  const m = Math.floor((ts % 3600) / 60);
  const s = (ts % 60).toFixed(2).padStart(5, "0");
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s}`;
}

export default function FrameModal({ item, onClose }) {
  useEffect(() => {
    if (!item) return;
    function onKey(e) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [item, onClose]);

  if (!item) return null;

  const text = item.text ?? item.target_text;

  return (
    <div
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="max-w-2xl w-full bg-base-900 border border-base-700 rounded-lg overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="bg-base-950 flex items-center justify-center">
          {item.frame_url ? (
            <img src={item.frame_url} alt={text} className="w-full h-auto" />
          ) : (
            <div className="h-56 flex items-center justify-center text-neutral-700 text-sm font-mono">
              no frame available
            </div>
          )}
        </div>
        <div className="p-5 flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-sm text-neutral-100">{text}</p>
            <p className="font-mono text-xs text-amber-500 mt-2">
              {formatTs(item.timestamp_sec)} · frame {item.frame_number}
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 text-neutral-500 hover:text-neutral-200 font-mono text-xs border border-base-600 rounded px-2.5 py-1.5"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
