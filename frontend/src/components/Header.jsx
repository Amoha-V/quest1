export default function Header() {
  return (
    <header className="border-b border-base-700">
      <div className="h-3 sprocket-strip" aria-hidden="true" />

      <div className="max-w-6xl mx-auto px-6 lg:px-8 pt-6">
        <nav className="flex items-center gap-1 font-mono text-xs text-neutral-600 tracking-wide">
          <span className="text-neutral-500">~/frame-finder</span>
          <span className="text-base-600">/</span>
          <a href="#results" className="hover:text-amber-500 transition-colors">
            results/
          </a>
          <span className="text-base-600">/</span>
          <a href="#timeline" className="hover:text-amber-500 transition-colors">
            timeline/
          </a>
        </nav>
      </div>

      <div className="max-w-6xl mx-auto px-6 lg:px-8 pb-10 pt-4 flex items-baseline justify-between">
        <div>
          <p className="section-marker font-mono text-xs uppercase tracking-widest text-neutral-500 mb-2">
            01 · Frame Finder
          </p>
          <h1 className="font-display text-5xl md:text-6xl font-semibold tracking-tight text-neutral-50">
            Frame Finder
          </h1>
          <p className="prompt font-mono text-sm md:text-base text-neutral-500 mt-2 tracking-wide">
            locate the exact frame a line was spoken
          </p>
        </div>
        <span className="hidden md:inline-block font-mono text-xs font-semibold text-amber-600 bg-amber-500/10 border border-amber-600/40 rounded px-2.5 py-1.5 tracking-widest">
          OCR · DBNet + CRNN
        </span>
      </div>

      <div className="h-3 sprocket-strip" aria-hidden="true" />
    </header>
  );
}