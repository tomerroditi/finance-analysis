import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Check, Search } from "lucide-react";

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
  const [search, setSearch] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0, openUp: false });

  const showSearch = options.length > 5;

  const filteredOptions = search
    ? options.filter((o) =>
        o.label.toLowerCase().includes(search.toLowerCase()),
      )
    : options;

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
    if (!isOpen) {
      setSearch("");
      setHighlightIndex(-1);
      return;
    }
    updatePosition();
    requestAnimationFrame(() => {
      if (showSearch) {
        searchRef.current?.focus();
      } else {
        dropdownRef.current?.focus();
      }
    });
    const onScroll = () => updatePosition();
    window.addEventListener("scroll", onScroll, true);
    window.addEventListener("resize", onScroll);
    return () => {
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onScroll);
    };
  }, [isOpen, updatePosition, showSearch]);

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

  // Reset highlight when filtered options change
  useEffect(() => {
    setHighlightIndex(-1);
  }, [search]);

  // Scroll highlighted item into view
  useEffect(() => {
    if (highlightIndex < 0 || !listRef.current) return;
    const items = listRef.current.children;
    if (items[highlightIndex]) {
      (items[highlightIndex] as HTMLElement).scrollIntoView({ block: "nearest" });
    }
  }, [highlightIndex]);

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (!isOpen) return;

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev < filteredOptions.length - 1 ? prev + 1 : 0,
          );
          break;
        case "ArrowUp":
          e.preventDefault();
          setHighlightIndex((prev) =>
            prev > 0 ? prev - 1 : filteredOptions.length - 1,
          );
          break;
        case "Enter":
          e.preventDefault();
          if (highlightIndex >= 0 && filteredOptions[highlightIndex]) {
            onChange(filteredOptions[highlightIndex].value);
            setIsOpen(false);
          }
          break;
        case "Escape":
          e.preventDefault();
          setIsOpen(false);
          buttonRef.current?.focus();
          break;
      }
    },
    [isOpen, highlightIndex, filteredOptions, onChange],
  );

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
        onKeyDown={(e) => {
          if (!isOpen && (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            setIsOpen(true);
          }
        }}
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
            tabIndex={-1}
            onKeyDown={handleKeyDown}
            className="fixed max-h-64 bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl shadow-xl flex flex-col outline-none"
            style={{
              top: pos.openUp ? undefined : pos.top + 4,
              bottom: pos.openUp
                ? window.innerHeight - pos.top + 4
                : undefined,
              left: pos.left,
              width: pos.width,
              zIndex: 9999,
            }}
          >
            {showSearch && (
              <div className="p-1.5 border-b border-[var(--surface-light)]">
                <div className="relative">
                  <Search
                    size={12}
                    className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                  />
                  <input
                    ref={searchRef}
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search..."
                    className="w-full pl-7 pr-2 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
                  />
                </div>
              </div>
            )}
            <div ref={listRef} className="overflow-y-auto flex-1">
              {filteredOptions.map((opt, idx) => (
                <button
                  key={opt.value}
                  type="button"
                  onMouseEnter={() => setHighlightIndex(idx)}
                  onClick={() => {
                    onChange(opt.value);
                    setIsOpen(false);
                  }}
                  className={`w-full flex items-center justify-between px-4 py-2.5 text-sm transition-colors text-left ${
                    idx === highlightIndex
                      ? "bg-[var(--surface-light)]"
                      : "hover:bg-[var(--surface-light)]"
                  }`}
                >
                  <span className="text-[var(--text-default)]">
                    {opt.label}
                  </span>
                  {value === opt.value && (
                    <Check
                      size={14}
                      className="text-[var(--primary)] shrink-0"
                    />
                  )}
                </button>
              ))}
              {filteredOptions.length === 0 && (
                <div className="px-4 py-3 text-sm text-[var(--text-muted)] text-center">
                  {search ? "No matches found" : "No options available"}
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
};
