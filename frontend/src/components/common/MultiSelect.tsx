import React, { useState, useRef, useEffect, useCallback } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, X, Check, CheckCheck, Search } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAnchoredPanel } from "../../hooks/useAnchoredPanel";
import { isTouchDevice } from "../../utils/chartStyle";

/** Tallest the panel grows. */
const PANEL_MAX_HEIGHT_PX = 208;

interface MultiSelectProps {
  options: string[];
  selected: string[];
  onChange: (selected: string[]) => void;
  placeholder?: string;
  /**
   * Offer a one-click "select all" row above the options.
   *
   * Opt-in, because it only makes sense where every option is a real choice —
   * a budget envelope covering its whole category. In a filter, selecting
   * everything is the same as selecting nothing, so the row would be a
   * control that does not do anything.
   */
  showSelectAll?: boolean;
}

export const MultiSelect: React.FC<MultiSelectProps> = ({
  options,
  selected,
  onChange,
  placeholder = "Select...",
  showSelectAll = false,
}) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const panelStyle = useAnchoredPanel(buttonRef, isOpen, {
    maxHeight: PANEL_MAX_HEIGHT_PX,
    minWidth: 220,
  });

  const closeDropdown = useCallback(() => {
    setIsOpen(false);
    setSearch("");
  }, []);

  // Typing straight away is the point on a desktop. On a phone it would pop
  // the keyboard on every open, shoving the screen around before the user
  // even looked at the options — they tap the search box when they want it.
  useEffect(() => {
    if (!isOpen || isTouchDevice) return;
    const frame = requestAnimationFrame(() =>
      searchRef.current?.focus({ preventScroll: true }),
    );
    return () => cancelAnimationFrame(frame);
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (
        buttonRef.current?.contains(target) ||
        dropdownRef.current?.contains(target)
      )
        return;
      closeDropdown();
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [isOpen, closeDropdown]);

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

  // Scoped to what the search box is showing: with a query typed, "select
  // all" means the matches in front of the user, not every hidden option —
  // and the label flips to the undo of exactly that.
  const allFilteredSelected =
    filteredOptions.length > 0 &&
    filteredOptions.every((opt) => selected.includes(opt));

  const toggleAllFiltered = () => {
    if (allFilteredSelected) {
      onChange(selected.filter((s) => !filteredOptions.includes(s)));
      return;
    }
    onChange([
      ...selected,
      ...filteredOptions.filter((opt) => !selected.includes(opt)),
    ]);
  };

  const clearAll = (e: React.MouseEvent) => {
    e.stopPropagation();
    onChange([]);
  };

  return (
    <div className="relative">
      <button
        ref={buttonRef}
        onClick={() => (isOpen ? closeDropdown() : setIsOpen(true))}
        type="button"
        className="w-full flex items-center justify-between px-2.5 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg hover:border-[var(--primary)]/50 transition-colors text-start"
      >
        <span
          className={`truncate ${selected.length === 0 ? "text-[var(--text-muted)]" : "text-[var(--text-default)]"}`}
        >
          {selected.length === 0
            ? placeholder
            : t("common.countSelected", { count: selected.length })}
        </span>
        <div className="flex items-center gap-1 ms-1 shrink-0">
          {selected.length > 0 && (
            <button
              type="button"
              onClick={clearAll}
              aria-label={t("common.clearSelection")}
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
              <span className="truncate" dir="auto">
                {s.length > 18 ? s.slice(0, 18) + "..." : s}
              </span>
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  toggle(s);
                }}
                aria-label={t("common.remove")}
                className="shrink-0 hover:text-red-400 transition-colors"
              >
                <X size={10} />
              </button>
            </span>
          ))}
          {selected.length > 2 && (
            <span className="text-[10px] text-[var(--text-muted)] py-0.5">
              {t("common.countMore", { count: selected.length - 2 })}
            </span>
          )}
        </div>
      )}

      {isOpen &&
        createPortal(
          <div
            ref={dropdownRef}
            data-testid="multiselect-panel"
            className="fixed bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg shadow-xl flex flex-col outline-none overflow-hidden"
            style={{ ...panelStyle, zIndex: 9999 }}
          >
            <div className="sticky top-0 p-1.5 bg-[var(--surface)] border-b border-[var(--surface-light)]">
              <div className="relative">
                <Search
                  size={12}
                  className="absolute start-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                />
                <input
                  ref={searchRef}
                  type="text"
                  inputMode="search"
                  enterKeyHint="search"
                  autoComplete="off"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("common.search") + "..."}
                  className="w-full ps-6 pe-2 py-1.5 text-xs bg-[var(--surface-base)] border border-[var(--surface-light)] rounded outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
                />
              </div>
            </div>
            {showSelectAll && filteredOptions.length > 0 && (
              <button
                type="button"
                data-testid="multiselect-select-all"
                onClick={toggleAllFiltered}
                className="w-full flex items-center gap-2 px-2.5 py-2 text-xs font-medium text-[var(--primary)] hover:bg-[var(--surface-light)] border-b border-[var(--surface-light)] transition-colors text-start"
              >
                <CheckCheck size={12} className="shrink-0" />
                <span className="truncate">
                  {allFilteredSelected
                    ? t("common.deselectAll")
                    : t("common.selectAll")}
                </span>
                <span className="ms-auto text-[10px] text-[var(--text-muted)]" dir="ltr">
                  {filteredOptions.length}
                </span>
              </button>
            )}
            <div role="listbox" aria-multiselectable="true" className="overflow-y-auto overscroll-contain flex-1 min-h-0">
              {filteredOptions.map((opt) => (
                <button
                  key={opt}
                  type="button"
                  role="option"
                  aria-selected={selected.includes(opt)}
                  onClick={() => toggle(opt)}
                  className="w-full flex items-center gap-2 px-2.5 py-2 text-xs hover:bg-[var(--surface-light)] transition-colors text-start"
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
                  <span className="truncate text-[var(--text-default)]" dir="auto">
                    {opt}
                  </span>
                </button>
              ))}
              {filteredOptions.length === 0 && (
                <div className="px-2.5 py-3 text-xs text-[var(--text-muted)] text-center">
                  {t("common.noMatchesFound")}
                </div>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
};
