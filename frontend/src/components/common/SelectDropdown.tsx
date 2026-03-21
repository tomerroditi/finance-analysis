import React, { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import { ChevronDown, Check, Search, Plus, X } from "lucide-react";

interface SelectDropdownProps {
  options: { label: string; value: string }[];
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  size?: "default" | "sm";
  onCreateNew?: (value: string) => Promise<void> | void;
}

export const SelectDropdown: React.FC<SelectDropdownProps> = ({
  options,
  value,
  onChange,
  placeholder = "Select...",
  required,
  disabled,
  size = "default",
  onCreateNew,
}) => {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [highlightIndex, setHighlightIndex] = useState(-1);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ top: 0, left: 0, width: 0, openUp: false });
  const [isCreating, setIsCreating] = useState(false);
  const [createValue, setCreateValue] = useState("");
  const createInputRef = useRef<HTMLInputElement>(null);

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
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setSearch("");
      setHighlightIndex(-1);
      setIsCreating(false);
      setCreateValue("");
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
    // eslint-disable-next-line react-hooks/set-state-in-effect
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

  const handleStartCreate = () => {
    setCreateValue(search);
    setIsCreating(true);
    requestAnimationFrame(() => createInputRef.current?.focus());
  };

  const handleConfirmCreate = async () => {
    const trimmed = createValue.trim();
    if (!trimmed) return;
    try {
      await onCreateNew?.(trimmed);
      setIsCreating(false);
      setCreateValue("");
      setIsOpen(false);
    } catch {
      // Stay in creation mode so user can retry
    }
  };

  const handleCancelCreate = () => {
    setIsCreating(false);
    setCreateValue("");
  };

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
        className={`w-full flex items-center justify-between bg-[var(--surface-base)] border border-[var(--surface-light)] outline-none transition-all text-start ${sizeClasses} ${
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
          className={`text-[var(--text-muted)] transition-transform shrink-0 ms-2 ${isOpen ? "rotate-180" : ""}`}
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
                    className="absolute start-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
                  />
                  <input
                    ref={searchRef}
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder={t("common.search") + "..."}
                    className="w-full ps-7 pe-2 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
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
                  className={`w-full flex items-center justify-between px-4 py-2.5 text-sm transition-colors text-start ${
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
                  {search ? t("common.noMatchesFound") : t("common.noOptionsAvailable")}
                </div>
              )}
              {onCreateNew && (
                <>
                  {(filteredOptions.length > 0 || isCreating) && (
                    <div className="border-t border-[var(--surface-light)]" />
                  )}
                  {isCreating ? (
                    <div className="p-1.5">
                      <div className="flex items-center gap-1">
                        <input
                          ref={createInputRef}
                          type="text"
                          value={createValue}
                          onChange={(e) => setCreateValue(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              e.preventDefault();
                              handleConfirmCreate();
                            } else if (e.key === "Escape") {
                              e.preventDefault();
                              handleCancelCreate();
                            }
                            e.stopPropagation();
                          }}
                          placeholder={t("common.enterName")}
                          className="flex-1 px-3 py-1.5 text-sm bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg outline-none focus:border-[var(--primary)] text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
                        />
                        <button
                          type="button"
                          onClick={handleConfirmCreate}
                          className="p-1.5 text-emerald-400 hover:bg-emerald-500/10 rounded-lg transition-colors"
                        >
                          <Check size={14} />
                        </button>
                        <button
                          type="button"
                          onClick={handleCancelCreate}
                          className="p-1.5 text-[var(--text-muted)] hover:bg-[var(--surface-light)] rounded-lg transition-colors"
                        >
                          <X size={14} />
                        </button>
                      </div>
                    </div>
                  ) : (
                    <button
                      type="button"
                      onClick={handleStartCreate}
                      className="w-full flex items-center gap-2 px-4 py-2.5 text-sm text-[var(--primary)] hover:bg-[var(--surface-light)] transition-colors"
                    >
                      <Plus size={14} />
                      {t("common.createNew")}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
};
