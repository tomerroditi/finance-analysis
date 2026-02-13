import React from "react";
import { X } from "lucide-react";
import { MultiSelect } from "../common/MultiSelect";
import type {
  TransactionFilterState,
  FilterOptions,
} from "../../hooks/useTransactionFilters";

interface FilterPanelProps {
  filters: TransactionFilterState;
  options: FilterOptions;
  onFilterChange: (updates: Partial<TransactionFilterState>) => void;
  onReset: () => void;
  activeFilterCount: number;
  compact?: boolean;
}

export const FilterPanel: React.FC<FilterPanelProps> = ({
  filters,
  options,
  onFilterChange,
  onReset,
  activeFilterCount,
  compact = false,
}) => {
  return (
    <div
      className={`w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl animate-in slide-in-from-top-2 fade-in duration-200 ${compact ? "p-3" : "p-4"}`}
    >
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider">
          Advanced Filters
        </h3>
        {activeFilterCount > 0 && (
          <button
            type="button"
            onClick={onReset}
            className="text-xs text-red-400 hover:text-red-300 transition-colors flex items-center gap-1"
          >
            <X size={12} /> Clear All
          </button>
        )}
      </div>

      <div
        className={`grid ${compact ? "grid-cols-2 gap-3" : "grid-cols-5 gap-4"}`}
      >
        {/* Account Multi-Select */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
            Account
          </label>
          <MultiSelect
            options={options.accounts}
            selected={filters.selectedAccounts}
            onChange={(v) => onFilterChange({ selectedAccounts: v })}
            placeholder="All accounts"
          />
        </div>

        {/* Category Multi-Select */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
            Category
          </label>
          <MultiSelect
            options={options.categories}
            selected={filters.selectedCategories}
            onChange={(v) => onFilterChange({ selectedCategories: v })}
            placeholder="All categories"
          />
        </div>

        {/* Tag Multi-Select */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
            Tag
          </label>
          <MultiSelect
            options={options.tags}
            selected={filters.selectedTags}
            onChange={(v) => onFilterChange({ selectedTags: v })}
            placeholder="All tags"
          />
        </div>

        {/* Amount Range */}
        <div>
          <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
            Amount Range
          </label>
          <div className="flex gap-2">
            <input
              type="number"
              placeholder="Min"
              value={filters.amountMin ?? ""}
              onChange={(e) =>
                onFilterChange({
                  amountMin: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full min-w-0 px-2.5 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] outline-none text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
            />
            <input
              type="number"
              placeholder="Max"
              value={filters.amountMax ?? ""}
              onChange={(e) =>
                onFilterChange({
                  amountMax: e.target.value ? Number(e.target.value) : null,
                })
              }
              className="w-full min-w-0 px-2.5 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] outline-none text-[var(--text-default)] placeholder:text-[var(--text-muted)]"
            />
          </div>
        </div>

        {/* Date Range */}
        <div className="min-w-0">
          <label className="text-xs font-medium text-[var(--text-muted)] mb-1.5 block">
            Date Range
          </label>
          <div className="flex gap-2">
            <input
              type="date"
              value={filters.dateStart ?? ""}
              onChange={(e) =>
                onFilterChange({
                  dateStart: e.target.value || null,
                })
              }
              className="w-full min-w-0 px-2 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] outline-none text-[var(--text-default)]"
            />
            <input
              type="date"
              value={filters.dateEnd ?? ""}
              onChange={(e) =>
                onFilterChange({
                  dateEnd: e.target.value || null,
                })
              }
              className="w-full min-w-0 px-2 py-1.5 text-xs bg-[var(--surface)] border border-[var(--surface-light)] rounded-lg focus:ring-1 focus:ring-[var(--primary)] focus:border-[var(--primary)] outline-none text-[var(--text-default)]"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
