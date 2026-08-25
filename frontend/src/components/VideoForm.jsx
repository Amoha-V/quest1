import { useState } from "react";

export default function VideoForm({ onSubmit, disabled }) {
  const [url, setUrl] = useState("");
  const [targetText, setTargetText] = useState("");

  function handleSubmit(e) {
    e.preventDefault();
    if (!url.trim()) return;
    onSubmit(url.trim(), targetText.trim());
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="bg-base-900 border border-base-700 rounded-lg p-5 md:p-6 space-y-4"
    >
      <div>
        <label
          htmlFor="video-url"
          className="block font-mono text-xs uppercase tracking-widest text-neutral-500 mb-1.5"
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
          className="w-full bg-base-800 border border-base-600 rounded-md px-3.5 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500 outline-none disabled:opacity-50"
        />
      </div>

      <div>
        <label
          htmlFor="target-text"
          className="block font-mono text-xs uppercase tracking-widest text-neutral-500 mb-1.5"
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
          className="w-full bg-base-800 border border-base-600 rounded-md px-3.5 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500 outline-none disabled:opacity-50"
        />
        <p className="text-xs text-neutral-600 mt-1.5">
          Leave blank to just extract every on-screen line. Set this to get a
          frame-accurate answer for one specific line.
        </p>
      </div>

      <button
        type="submit"
        disabled={disabled || !url.trim()}
        className="w-full md:w-auto inline-flex items-center justify-center gap-2 bg-amber-500 hover:bg-amber-400 disabled:bg-base-600 disabled:text-neutral-500 text-base-950 font-semibold text-sm rounded-md px-5 py-2.5 transition-colors"
      >
        {disabled ? "Processing…" : "Find frames"}
      </button>
    </form>
  );
}
