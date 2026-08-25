import { useEffect, useState } from "react";

export default function SearchBar({ onQueryChange, count }) {
  const [value, setValue] = useState("");

  useEffect(() => {
    const t = setTimeout(() => onQueryChange(value.trim()), 250);
    return () => clearTimeout(t);
  }, [value, onQueryChange]);

  return (
    <div className="flex items-center gap-3">
      <div className="relative flex-1">
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Search detected dialogue…"
          className="w-full bg-base-800 border border-base-600 rounded-md pl-9 pr-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-amber-500 outline-none"
        />
        <svg
          className="absolute left-2.5 top-1/2 -translate-y-1/2 w-4 h-4 text-neutral-600"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth="2"
        >
          <circle cx="11" cy="11" r="7" />
          <path d="m21 21-4.35-4.35" strokeLinecap="round" />
        </svg>
      </div>
      <span className="font-mono text-xs text-neutral-600 shrink-0">
        {count} {count === 1 ? "line" : "lines"}
      </span>
    </div>
  );
}
