export default function Header() {
  return (
    <header className="border-b border-base-700">
      <div className="h-3 sprocket-strip" aria-hidden="true" />
      <div className="max-w-5xl mx-auto px-6 py-8 flex items-baseline justify-between">
        <div>
          <h1 className="font-display text-3xl md:text-4xl font-semibold tracking-tight text-neutral-50">
            Frame Finder
          </h1>
          <p className="font-mono text-xs md:text-sm text-neutral-500 mt-1 tracking-wide">
            00:00:00:00 — locate the exact frame a line was spoken
          </p>
        </div>
        <span className="hidden md:inline-block font-mono text-[11px] text-amber-500 border border-amber-600/40 rounded px-2 py-1 tracking-widest">
          OCR · DBNet + CRNN
        </span>
      </div>
      <div className="h-3 sprocket-strip" aria-hidden="true" />
    </header>
  );
}
