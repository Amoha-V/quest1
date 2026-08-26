import { useState } from "react";

export default function VideoForm({ onSubmit, disabled }) {
  const [url, setUrl] = useState("");
  const [targetText, setTargetText] = useState("My mind rebels at stagnation");
  const [scanAll, setScanAll] = useState(false);

  function handleSubmit(e) {
    e.preventDefault();
    if (!url.trim()) return;
    onSubmit(url.trim(), targetText.trim(), scanAll);
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-base-900 border border-base-700 rounded-lg p-6 md:p-8 space-y-5"
    >
      <div>
        <label
          htmlFor="video-url"
          className="block font-mono text-xs uppercase tracking-widest text-neutral-500 mb-2"
        >
          Video URL
        </label>
        <input
          id="video-url"
          type="text"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://ok.ru/video/248244667877"
          disabled={disabled}
          className="w-full bg-base-800 border border-base-600 rounded-md px-4 py-3 text-base text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500 outline-none disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor="target-text"
          className="block font-mono text-xs uppercase tracking-widest text-neutral-500 mb-2"
        >
          Target dialogue <span className="text-neutral-600">(optional)</span>
        </label>
        <input
          id="target-text"
          type="text"
          value={targetText}
          onChange={(e) => setTargetText(e.target.value)}
          placeholder="My mind rebels at stagnation"
          disabled={disabled}
          className="w-full bg-base-800 border border-base-600 rounded-md px-4 py-3 text-base text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500 outline-none disabled:opacity-50"
        />
        <p className="text-sm text-neutral-600 mt-2">
          By default the pipeline finds the first appearance of this line
          (or the first on-screen dialogue if blank) and stops. Submitting
          the same URL and dialogue again loads the cached result.
        </p>
      </div>

      <label className="flex items-start gap-3 cursor-pointer select-none">
        <input
          type="checkbox"
          checked={scanAll}
          onChange={(e) => setScanAll(e.target.checked)}
          disabled={disabled}
          className="mt-1 h-4 w-4 rounded border-base-600 bg-base-800 text-amber-500 focus:ring-amber-500 focus:ring-offset-0"
        />
        <span>
          <span className="block text-sm text-neutral-200">
            Show all frames with dialogues
          </span>
          <span className="block text-sm text-neutral-600 mt-0.5">
            Optional. Walks the whole video and lists every distinct
            on-screen line instead of stopping at the first.
          </span>
        </span>
      </label>

      <button
        type="submit"
        disabled={disabled || !url.trim()}
        className="w-full md:w-auto inline-flex items-center justify-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:bg-base-600 disabled:text-neutral-500 text-base-950 font-semibold text-base rounded-md px-6 py-3 transition-colors"
      >
        {disabled ? "Processing…" : scanAll ? "Scan all dialogues" : "Find first dialogue"}
      </button>
    </form>
  );
}
