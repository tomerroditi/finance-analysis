import React, { useState, useRef, useEffect } from "react";
import { ChevronDown, Check } from "lucide-react";

interface SelectDropdownProps {
  options: { label: string; value: string }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
}

export const SelectDropdown: React.FC<SelectDropdownProps> = ({
  options,
  value,
  onChange,
  placeholder = "Select...",
  required,
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const selectedLabel = options.find((o) => o.value === value)?.label;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        type="button"
        className="w-full flex items-center justify-between bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none hover:border-[var(--primary)] focus:border-[var(--primary)] transition-all cursor-pointer text-left"
      >
        <span className={selectedLabel ? "text-[var(--text-default)]" : "text-[var(--text-muted)]"}>
          {selectedLabel || placeholder}
        </span>
        <ChevronDown
          size={16}
          className={`text-[var(--text-muted)] transition-transform ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

      {/* Hidden input for form validation */}
      {required && (
        <input
          type="text"
          value={value}
          required
          onChange={() => {}}
          className="sr-only"
          tabIndex={-1}
          aria-hidden="true"
        />
      )}

      {isOpen && (
        <div className="absolute z-50 top-full mt-1 w-full max-h-48 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl overflow-y-auto">
          {options.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => {
                onChange(opt.value);
                setIsOpen(false);
              }}
              className="w-full flex items-center justify-between px-4 py-2.5 text-sm hover:bg-[var(--surface-light)] transition-colors text-left"
            >
              <span className="text-[var(--text-default)]">{opt.label}</span>
              {value === opt.value && (
                <Check size={14} className="text-[var(--primary)] shrink-0" />
              )}
            </button>
          ))}
          {options.length === 0 && (
            <div className="px-4 py-3 text-sm text-[var(--text-muted)] text-center">
              No options available
            </div>
          )}
        </div>
      )}
    </div>
  );
};
