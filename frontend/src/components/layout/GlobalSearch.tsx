// TODO: Remove this feature entirely — not useful enough to justify the code/UX surface area.
// Files to clean up: GlobalSearch.tsx, Layout.tsx (keyboard listener + render), appStore.ts (isSearchOpen state), locale keys (globalSearch.*).
import React, { useState, useEffect, useRef, useCallback } from "react";
import { useScrollLock } from "../../hooks/useScrollLock";
import {
  Search as SearchIcon,
  X,
  Receipt,
  Tags,
  ArrowRight,
} from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { transactionsApi, taggingApi } from "../../services/api";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";

interface GlobalSearchProps {
  isOpen: boolean;
  onClose: () => void;
}

export function GlobalSearch({ isOpen, onClose }: GlobalSearchProps) {
  useScrollLock(isOpen);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const navigate = useNavigate();
  const { t } = useTranslation();

  const { data: transactions } = useQuery({
    queryKey: ["transactions", "search"],
    queryFn: () => transactionsApi.getAll().then((res) => res.data),
    enabled: isOpen && query.length > 2,
  });

  const { data: categories } = useQuery({
    queryKey: ["categories", "search"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
    enabled: isOpen,
  });

  const searchResults = React.useMemo(() => {
    if (!query || query.length < 2) return [];

    const results: { type: string; title: string; subtitle?: string; id: string; data?: unknown }[] = [];
    const q = query.toLowerCase();

    // 1. Search Categories & Tags
    if (categories) {
      Object.entries(categories).forEach(([cat, tags]: [string, unknown]) => {
        const tagList = tags as string[];
        if (cat.toLowerCase().includes(q)) {
          results.push({ type: "category", title: cat, id: `cat-${cat}` });
        }
        tagList.forEach((tag: string) => {
          if (tag.toLowerCase().includes(q)) {
            results.push({
              type: "tag",
              title: tag,
              subtitle: `in ${cat}`,
              id: `tag-${cat}-${tag}`,
            });
          }
        });
      });
    }

    // 2. Search Transactions
    if (transactions) {
      transactions
        .filter(
          (tx: Record<string, unknown>) =>
            (tx.description as string)?.toLowerCase().includes(q) ||
            (tx.category as string)?.toLowerCase().includes(q) ||
            (tx.tag as string)?.toLowerCase().includes(q),
        )
        .slice(0, 5)
        .forEach((tx: Record<string, unknown>) => {
          results.push({
            type: "transaction",
            title: String(tx.description ?? ""),
            subtitle: `${tx.date} • ₪${tx.amount}`,
            id: `tx-${tx.source}-${tx.unique_id}`,
            data: tx,
          });
        });
    }

    return results.slice(0, 10);
  }, [query, transactions, categories]);

  const handleSelect = useCallback((result: { type: string; id: string }) => {
    if (result.type === "transaction") {
      navigate("/transactions", { state: { highlightId: result.id } });
    } else if (result.type === "category" || result.type === "tag") {
      navigate("/categories");
    }
    onClose();
  }, [navigate, onClose]);

   
  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setQuery("");
       
      setSelectedIndex(0);
      setTimeout(() => inputRef.current?.focus(), 100);
    }
  }, [isOpen]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (!isOpen) return;

      if (e.key === "ArrowDown") {
        setSelectedIndex((prev) =>
          Math.min(prev + 1, searchResults.length - 1),
        );
      } else if (e.key === "ArrowUp") {
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === "Enter" && searchResults[selectedIndex]) {
        handleSelect(searchResults[selectedIndex]);
      } else if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
     
  }, [isOpen, searchResults, selectedIndex, onClose, handleSelect]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center pt-[10vh] md:pt-[15vh] px-3 md:px-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 modal-overlay"
      onClick={onClose}
    >
      <div
        className="bg-[var(--surface)] w-full max-w-[calc(100vw-1.5rem)] md:max-w-2xl rounded-2xl border border-[var(--surface-light)] shadow-2xl overflow-hidden animate-in zoom-in-95 duration-200"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="relative border-b border-[var(--surface-light)] bg-[var(--surface-light)]/20">
          <SearchIcon
            className="absolute start-5 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
            size={20}
          />
          <input
            ref={inputRef}
            type="text"
            placeholder={t("globalSearch.placeholder")}
            aria-label={t("globalSearch.placeholder")}
            className="w-full bg-transparent ps-14 pe-16 py-5 text-lg outline-none text-white placeholder-[var(--text-muted)]"
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
          />
          <div className="absolute end-5 top-1/2 -translate-y-1/2 flex items-center gap-2">
            <span className="px-1.5 py-0.5 rounded border border-[var(--surface-light)] bg-[var(--surface)] text-[10px] text-[var(--text-muted)] font-mono">
              ESC
            </span>
            <button
              onClick={onClose}
              aria-label={t("common.close")}
              className="p-1 hover:bg-[var(--surface-light)] rounded-lg transition-colors"
            >
              <X size={18} />
            </button>
          </div>
        </div>

        <div className="max-h-[60vh] overflow-y-auto p-2">
          {query.length > 0 && query.length < 2 && (
            <div className="p-8 text-center text-[var(--text-muted)] text-sm">
              {t("globalSearch.minChars")}
            </div>
          )}

          {query.length >= 2 && searchResults.length === 0 && (
            <div className="p-8 text-center text-[var(--text-muted)] text-sm">
              {t("globalSearch.noResults")} "{query}"
            </div>
          )}

          {searchResults.map((result, index) => (
            <div
              key={result.id}
              className={`flex items-center justify-between p-4 rounded-xl cursor-pointer transition-all ${
                index === selectedIndex
                  ? "bg-[var(--primary)]/10 border border-[var(--primary)]/30"
                  : "hover:bg-[var(--surface-light)]/50 border border-transparent"
              }`}
              onMouseEnter={() => setSelectedIndex(index)}
              onClick={() => handleSelect(result)}
            >
              <div className="flex items-center gap-4">
                <div
                  className={`p-2.5 rounded-xl ${
                    result.type === "transaction"
                      ? "bg-amber-500/10 text-amber-400"
                      : result.type === "category"
                        ? "bg-blue-500/10 text-blue-400"
                        : "bg-purple-500/10 text-purple-400"
                  }`}
                >
                  {result.type === "transaction" ? (
                    <Receipt size={20} />
                  ) : (
                    <Tags size={20} />
                  )}
                </div>
                <div>
                  <div className="text-sm font-bold text-white">
                    {result.title}
                  </div>
                  {result.subtitle && (
                    <div className="text-xs text-[var(--text-muted)] mt-0.5 lowercase tracking-tight">
                      {result.subtitle}
                    </div>
                  )}
                </div>
              </div>
              {index === selectedIndex && (
                <div className="flex items-center gap-2 text-[var(--primary)] animate-in slide-in-from-right-2 duration-200">
                  <span className="text-xs font-bold uppercase tracking-widest">
                    Select
                  </span>
                  <ArrowRight size={16} />
                </div>
              )}
            </div>
          ))}
        </div>

        {query.length === 0 && (
          <div className="p-8 text-center">
            <div className="flex justify-center mb-4">
              <div className="p-4 rounded-full bg-[var(--primary)]/10 text-[var(--primary)]">
                <SearchIcon size={32} />
              </div>
            </div>
            <h3 className="text-white font-bold">{t("globalSearch.shortcut")}</h3>
            <p className="text-sm text-[var(--text-muted)] mt-1 max-w-xs mx-auto">
              {t("globalSearch.placeholder")}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
