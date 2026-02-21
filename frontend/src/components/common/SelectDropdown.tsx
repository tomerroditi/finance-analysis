import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Check } from "lucide-react";

interface SelectDropdownProps {
  options: { label: string; value: string }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  size?: "default" | "sm";
}

export const SelectDropdown: React.FC<SelectDropdownProps> = ({
  options,
  value,
  onChange,
  placeholder = "Select...",
  required,
  disabled,
  size = "default",
}) => {
  const [isOpen, setIsOpen] = useState(false);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0, openUp: false });

  const updatePosition = useCallback(() => {
    if (!buttonRef.current) return;
    const rect = buttonRef.current.getBoundingClientRect();
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUp = spaceBelow < 200 && rect.top > spaceBelow;
    setPos({
      top: openUp ? rect.top : rect.bottom,
      left: rect.left,
      width: rect.width,
      openUp,
    });
  }, []);

  useEffect(() => {
    if (!isOpen) return;
    updatePosition();
    const onScroll = () => updatePosition();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [isOpen, updatePosition]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        buttonRef.current?.contains(target) ||
        dropdownRef.current?.contains(target)
      )
        return;
      setIsOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen]);

  const selectedLabel = options.find((o) => o.value === value)?.label;

  const sizeClasses =
    size === "sm"
      ? "px-3 py-1.5 text-sm rounded-lg"
      : "px-4 py-2.5 text-sm rounded-xl";

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => !disabled && setIsOpen(!isOpen)}
        type="button"
        className={`w-full flex items-center justify-between bg-[var(--surface-base)] border border-[var(--surface-light)] outline-none transition-all text-left ${sizeClasses} ${
          disabled
            ? "opacity-50 cursor-not-allowed"
            : "hover:border-[var(--primary)] focus:border-[var(--primary)] cursor-pointer"
        }`}
      >
        <span
          className={
            selectedLabel
              ? "text-[var(--text-default)]"
              : "text-[var(--text-muted)]"
          }
        >
          {selectedLabel || placeholder}
        </span>
        <ChevronDown
          size={size === "sm" ? 14 : 16}
          className={`text-[var(--text-muted)] transition-transform shrink-0 ml-2 ${isOpen ? "rotate-180" : ""}`}
        />
      </button>

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

      {isOpen &&
        !disabled &&
        createPortal(
          <div
            ref={dropdownRef}
            className="fixed max-h-48 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl overflow-y-auto"
            style={{
              top: pos.openUp ? undefined : pos.top + 4,
              bottom: pos.openUp ? window.innerHeight - pos.top + 4 : undefined,
              left: pos.left,
              width: pos.width,
              zIndex: 9999,
            }}
          >
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
                  <Check
                    size={14}
                    className="text-[var(--primary)] shrink-0"
                  />
                )}
              </button>
            ))}
            {options.length === 0 && (
              <div className="px-4 py-3 text-sm text-[var(--text-muted)] text-center">
                No options available
              </div>
            )}
          </div>,
          document.body,
        )}
    </div>
  );
};
