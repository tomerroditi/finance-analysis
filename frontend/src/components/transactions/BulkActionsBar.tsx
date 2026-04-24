import { CheckCircle2, Trash2, X } from "lucide-react";
import { SelectDropdown } from "../common/SelectDropdown";
import { useTranslation } from "react-i18next";

export interface BulkEditData {
  date: string;
  description: string;
  amount: string;
  account_name: string;
  category: string;
  tag: string;
}

interface BulkActionsBarProps {
  selectedCount: number;
  bulkEditData: BulkEditData;
  onBulkEditDataChange: (data: BulkEditData) => void;
  amountType: "expense" | "income";
  onAmountTypeChange: (type: "expense" | "income") => void;
  allSelectedAreManual: boolean;
  allSelectedAreCash: boolean;
  categories: Record<string, string[]> | undefined;
  cashBalances: { account_name: string }[];
  onApply: () => void;
  onBulkDelete: () => void;
  onClearSelection: () => void;
  onCreateCategory: (name: string) => Promise<string>;
  onCreateTag: (category: string, name: string) => Promise<string>;
  isApplying: boolean;
  showDelete: boolean;
}

export function BulkActionsBar({
  selectedCount,
  bulkEditData,
  onBulkEditDataChange,
  amountType,
  onAmountTypeChange,
  allSelectedAreManual,
  allSelectedAreCash,
  categories,
  cashBalances,
  onApply,
  onBulkDelete,
  onClearSelection,
  onCreateCategory,
  onCreateTag,
  isApplying,
  showDelete,
}: BulkActionsBarProps) {
  const { t } = useTranslation();

  return (
    <div className="fixed bottom-4 md:bottom-8 inset-x-4 md:inset-x-auto md:left-1/2 md:-translate-x-1/2 bg-[var(--surface)] backdrop-blur-xl border-2 border-[var(--primary)] rounded-2xl shadow-[0_0_40px_rgba(0,0,0,0.5)] px-4 md:px-6 py-3 md:py-4 flex flex-wrap items-center gap-3 md:gap-6 animate-in fade-in slide-in-from-bottom-4 duration-300 z-40 max-h-[60vh] overflow-y-auto">
      <div className="flex items-center gap-2">
        <div className="w-8 h-8 rounded-full bg-[var(--primary)] flex items-center justify-center text-sm font-bold shadow-lg shadow-[var(--primary)]/20">
          {selectedCount}
        </div>
        <span className="text-sm font-medium">{t("transactions.bulk.selected")}</span>
      </div>
      <div className="w-px h-8 bg-[var(--surface-light)]" />
      <div className="flex items-center gap-3 flex-wrap">
        {/* Details group - only for manual transactions */}
        {allSelectedAreManual && (
          <>
            <span className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">{t("transactions.bulk.details")}</span>
            <input
              type="date"
              value={bulkEditData.date}
              onChange={(e) => onBulkEditDataChange({ ...bulkEditData, date: e.target.value })}
              className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-36 focus:outline-none focus:border-[var(--primary)]/50"
              placeholder={t("common.date")}
            />
            <input
              type="text"
              value={bulkEditData.description}
              onChange={(e) => onBulkEditDataChange({ ...bulkEditData, description: e.target.value })}
              className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-40 focus:outline-none focus:border-[var(--primary)]/50"
              placeholder={t("common.description")}
            />
            <div className="flex bg-[var(--surface-light)] rounded-lg border border-[var(--surface-light)] p-0.5">
              <button
                type="button"
                onClick={() => onAmountTypeChange("expense")}
                className={`px-2 py-1 rounded-md text-xs font-medium transition-all ${amountType === "expense" ? "bg-red-500/20 text-red-500" : "text-[var(--text-muted)] hover:text-[var(--text-default)]"}`}
              >
                {t("transactions.bulk.expense")}
              </button>
              <button
                type="button"
                onClick={() => onAmountTypeChange("income")}
                className={`px-2 py-1 rounded-md text-xs font-medium transition-all ${amountType === "income" ? "bg-emerald-500/20 text-emerald-500" : "text-[var(--text-muted)] hover:text-[var(--text-default)]"}`}
              >
                {t("transactions.bulk.income")}
              </button>
            </div>
            <input
              type="number"
              value={bulkEditData.amount}
              onChange={(e) => onBulkEditDataChange({ ...bulkEditData, amount: e.target.value })}
              className="bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-lg px-3 py-1.5 text-sm w-28 focus:outline-none focus:border-[var(--primary)]/50"
              placeholder={t("common.amount")}
              step="0.01"
            />
            <div className="w-36">
              <SelectDropdown
                options={
                  allSelectedAreCash
                    ? cashBalances.map((b) => ({ label: b.account_name, value: b.account_name }))
                    : []
                }
                value={bulkEditData.account_name}
                onChange={(val) => onBulkEditDataChange({ ...bulkEditData, account_name: val })}
                placeholder={t("common.account")}
                size="sm"
              />
            </div>
            <div className="w-px h-6 bg-[var(--surface-light)]" />
          </>
        )}
        {/* Tags group - always visible */}
        <span className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wider">{t("transactions.bulk.tags")}</span>
        <div className="w-40">
          <SelectDropdown
            options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
            value={bulkEditData.category}
            onChange={(val) => onBulkEditDataChange({ ...bulkEditData, category: val, tag: "" })}
            placeholder={t("common.category")}
            size="sm"
            onCreateNew={async (name) => {
              const formatted = await onCreateCategory(name);
              onBulkEditDataChange({ ...bulkEditData, category: formatted, tag: "" });
            }}
          />
        </div>
        <div className="w-40">
          <SelectDropdown
            options={
              bulkEditData.category && categories?.[bulkEditData.category]
                ? categories[bulkEditData.category].map((tag: string) => ({ label: tag, value: tag }))
                : []
            }
            value={bulkEditData.tag}
            onChange={(val) => onBulkEditDataChange({ ...bulkEditData, tag: val })}
            placeholder={t("common.tag")}
            size="sm"
            onCreateNew={async (name) => {
              const formatted = await onCreateTag(bulkEditData.category, name);
              onBulkEditDataChange({ ...bulkEditData, tag: formatted });
            }}
          />
        </div>
        <div className="w-px h-6 bg-[var(--surface-light)]" />
        {/* Actions */}
        <button
          className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 disabled:opacity-50"
          onClick={onApply}
          disabled={isApplying}
          title={t("tooltips.applyChanges")}
        >
          <CheckCircle2 size={20} />
        </button>
        {showDelete && (
          <button
            className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-400 transition-all"
            onClick={onBulkDelete}
            title={t("tooltips.deleteSelected")}
          >
            <Trash2 size={18} />
          </button>
        )}
        <button
          className="p-1.5 rounded-lg hover:bg-[var(--surface-light)] text-[var(--text-muted)]"
          onClick={onClearSelection}
          title={t("tooltips.cancelSelection")}
        >
          <X size={20} />
        </button>
      </div>
    </div>
  );
}
