import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { CategoryCard } from "./CategoryCard";
import { formatMonthYear } from "../../utils/dateFormatting";

interface CategoryUsage {
  last_used: string | null;
  unused: boolean;
}

interface UnusedCategoriesSectionProps {
  /** Unused categories as [name, tags] pairs, already filtered and sorted. */
  entries: [string, string[]][];
  icons: Record<string, string>;
  usage: Record<string, CategoryUsage>;
  /** Controlled by the parent so a search can force the section open. */
  expanded: boolean;
  onToggle: () => void;
  onSelect: (category: string) => void;
}

/**
 * Collapsed disclosure holding categories that have gone quiet, keeping the
 * main grid lean as categories accumulate. Display-only: these categories are
 * still fully usable everywhere else in the app.
 */
export function UnusedCategoriesSection({
  entries,
  icons,
  usage,
  expanded,
  onToggle,
  onSelect,
}: UnusedCategoriesSectionProps) {
  const { t } = useTranslation();

  if (entries.length === 0) return null;

  return (
    <div className="border border-[var(--surface-light)] rounded-xl overflow-hidden">
      <button
        data-testid="unused-categories-toggle"
        onClick={onToggle}
        aria-expanded={expanded}
        className="w-full flex items-center gap-3 px-4 py-3 text-start hover:bg-[var(--surface-light)]/30 transition-colors"
      >
        <ChevronDown
          size={16}
          className={`shrink-0 text-[var(--text-muted)] transition-transform ${
            expanded ? "" : "-rotate-90 rtl:rotate-90"
          }`}
        />
        <span className="font-bold text-sm">
          {t("categories.unusedSection")}
        </span>
        <span className="text-xs text-[var(--text-muted)]" dir="ltr">
          ({entries.length})
        </span>
        <span className="ms-auto text-xs text-[var(--text-muted)] hidden sm:inline">
          {t("categories.unusedHint")}
        </span>
      </button>

      {expanded && (
        <div
          data-testid="unused-categories-grid"
          className="grid grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-3 p-3"
        >
          {entries.map(([category]) => {
            const lastUsed = usage[category]?.last_used;
            return (
              <CategoryCard
                key={category}
                category={category}
                icon={icons[category]}
                muted
                subtitle={
                  lastUsed
                    ? t("categories.lastUsed", {
                        date: formatMonthYear(lastUsed),
                      })
                    : t("categories.neverUsed")
                }
                onClick={() => onSelect(category)}
              />
            );
          })}
        </div>
      )}
    </div>
  );
}
