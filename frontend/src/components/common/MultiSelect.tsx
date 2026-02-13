import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, X, Check, Search } from "lucide-react";

interface MultiSelectProps {
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
}

export const MultiSelect: React.FC<MultiSelectProps> = ({
  options,
  selected,
  onChange,
  placeholder = "Select...",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
        setSearch("");
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const filteredOptions = options.filter((opt) =>
    opt.toLowerCase().includes(search.toLowerCase()),
  );

  const toggle = (option: string) => {
    if (selected.includes(option)) {
      onChange(selected.filter((s) => s !== option));
    } else {
      onChange([...selected, option]);
    }
  };

  const clearAll = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange([]);
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg hover:border-[var(--primary)]/50 transition-colors text-left"
      >
        <span
          className={`truncate ${selected.length === 0 ? "text-[var(--text-muted)]" : "text-[var(--text-default)]"}`}
        >
          {selected.length === 0
            ? placeholder
            : `${selected.length} selected`}
        </span>
        <div className="flex items-center gap-1 ml-1 shrink-0">
          {selected.length > 0 && (
            <button
              type="button"
              onClick={clearAll}
              className="p-0.5 hover:bg-[var(--surface-light)] rounded transition-colors"
            >
              <X size={10} className="text-[var(--text-muted)]" />
            </button>
          )}
          <ChevronDown
            size={12}
            className={`text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`}
          />
        </div>
      </button>

      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1">
          {selected.slice(0, 2).map((s) => (
            <span
              key={s}
              className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded bg-[var(--primary)]/10 text-[var(--primary)] text-[10px] font-medium max-w-full"
            >
              <span className="truncate">
                {s.length > 18 ? s.slice(0, 18) + "..." : s}
              </span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(s);
                }}
                className="shrink-0 hover:text-red-400 transition-colors"
              >
                <X size={10} />
              </button>
            </span>
          ))}
          {selected.length > 2 && (
            <span className="text-[10px] text-[var(--text-muted)] py-0.5">
              +{selected.length - 2} more
            </span>
          )}
        </div>
      )}

      {isOpen && (
        <div className="absolute z-50 top-full mt-1 w-full max-h-52 bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-xl flex flex-col">
          <div className="sticky top-0 p-1.5 bg-[var(--surface)] border-b border-[var(--surface-light)]">
            <div className="relative">
              <Search
                size={12}
                className="absolute left-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
              />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search..."
                className="w-full pl-6 pr-2 py-1 text-xs bg-[var(--surface-base)] border border-[var(--surface-light)] rounded outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
                autoFocus
              />
            </div>
          </div>
          <div className="overflow-y-auto flex-1">
            {filteredOptions.map((opt) => (
              <button
                key={opt}
                type="button"
                onClick={() => toggle(opt)}
                className="w-full flex items-center gap-2 px-2.5 py-1.5 text-xs hover:bg-[var(--surface-light)] transition-colors text-left"
              >
                <div
                  className={`w-3.5 h-3.5 rounded border flex items-center justify-center shrink-0 transition-colors ${
                    selected.includes(opt)
                      ? "bg-[var(--primary)] border-[var(--primary)]"
                      : "border-[var(--surface-light)]"
                  }`}
                >
                  {selected.includes(opt) && (
                    <Check size={10} className="text-white" />
                  )}
                </div>
                <span className="truncate text-[var(--text-default)]">
                  {opt}
                </span>
              </button>
            ))}
            {filteredOptions.length === 0 && (
              <div className="px-2.5 py-3 text-xs text-[var(--text-muted)] text-center">
                No options found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
