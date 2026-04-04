import React, { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2, AlertCircle } from "lucide-react";
import { transactionsApi } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { Modal } from "../common/Modal";
import { formatCurrency } from "../../utils/numberFormatting";

interface SplitTransactionModalProps {
  transaction: { id?: number; unique_id?: string; amount: number; source?: string; description?: string; desc?: string; category?: string; tag?: string };
  onClose: () => void;
  onSuccess: () => void;
}

interface SplitItem {
  amount: number;
  category: string;
  tag: string;
}

export function SplitTransactionModal({
  transaction,
  onClose,
  onSuccess,
}: SplitTransactionModalProps) {
  const { t } = useTranslation();
  const originalAmount = Number(transaction.amount);
  const [splits, setSplits] = useState<SplitItem[]>([
    {
      amount: originalAmount / 2,
      category: transaction.category || "",
      tag: transaction.tag || "",
    },
    { amount: originalAmount / 2, category: "", tag: "" },
  ]);

  const { createCategory, createTag } = useCategoryTagCreate();

  const { data: categories } = useCategories();

  const totalSplitAmount = useMemo(
    () => splits.reduce((sum, item) => sum + item.amount, 0),
    [splits],
  );
  const remainingAmount = originalAmount - totalSplitAmount;
  const isValid =
    Math.abs(remainingAmount) < 0.01 &&
    splits.every((s) => s.category && s.amount !== 0);

  const addSplit = () => {
    setSplits([...splits, { amount: 0, category: "", tag: "" }]);
  };

  const removeSplit = (index: number) => {
    if (splits.length <= 2) return;
    setSplits(splits.filter((_, i) => i !== index));
  };

  const updateSplit = (index: number, field: keyof SplitItem, value: string | number) => {
    const newSplits = [...splits];
    newSplits[index] = { ...newSplits[index], [field]: value };
    if (field === "category") newSplits[index].tag = ""; // Reset tag on category change
    setSplits(newSplits);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!isValid) return;

    try {
      await transactionsApi.split(transaction.id ?? 0, {
        source: transaction.source || "",
        splits: splits.map((s) => ({
          amount: s.amount,
          category: s.category,
          tag: s.tag,
        })),
      });
      onSuccess();
      onClose();
    } catch {
      alert("Failed to split transaction.");
    }
  };

  return (
    <Modal
      isOpen={true}
      onClose={onClose}
      title={t("modals.split.title")}
      titleId="split-transaction-title"
      maxWidth="2xl"
    >
        <div className="px-4 md:px-6 pb-2 text-sm text-[var(--text-muted)]">
          {transaction.description} • {formatCurrency(originalAmount, 2)}
        </div>

        <div className="p-4 md:p-6 overflow-y-auto flex-1">
          <div className="space-y-4">
            {splits.map((split, index) => (
              <div
                key={index}
                className="flex flex-col sm:flex-row gap-4 sm:items-end bg-[var(--surface-base)]/50 p-4 rounded-xl border border-[var(--surface-light)]"
              >
                <div className="flex-1 space-y-2">
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider ms-1">
                    {t("common.amount")}
                  </label>
                  <div className="relative">
                    <span className="absolute start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]">
                      ₪
                    </span>
                    <input
                      type="number"
                      step="0.01"
                      value={split.amount}
                      onChange={(e) =>
                        updateSplit(
                          index,
                          "amount",
                          parseFloat(e.target.value) || 0,
                        )
                      }
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-lg ps-8 pe-3 py-2 text-sm outline-none focus:border-[var(--primary)] transition-all"
                    />
                  </div>
                </div>

                <div className="flex-[1.5] space-y-2">
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider ms-1">
                    {t("common.category")}
                  </label>
                  <SelectDropdown
                    options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
                    value={split.category}
                    onChange={(val) => updateSplit(index, "category", val)}
                    placeholder={t("modals.transactionForm.selectCategory")}
                    size="sm"
                    onCreateNew={async (name) => {
                      const formatted = await createCategory(name);
                      updateSplit(index, "category", formatted);
                    }}
                  />
                </div>

                <div className="flex-[1.5] space-y-2">
                  <label className="block text-[10px] font-bold text-[var(--text-muted)] uppercase tracking-wider ms-1">
                    {t("common.tag")}
                  </label>
                  <SelectDropdown
                    options={split.category && categories?.[split.category] ? categories[split.category].map((tag: string) => ({ label: tag, value: tag })) : []}
                    value={split.tag}
                    onChange={(val) => updateSplit(index, "tag", val)}
                    placeholder={t("modals.transactionForm.selectTag")}
                    disabled={!split.category}
                    size="sm"
                    onCreateNew={async (name) => {
                      const formatted = await createTag(split.category, name);
                      updateSplit(index, "tag", formatted);
                    }}
                  />
                </div>

                <button
                  onClick={() => removeSplit(index)}
                  disabled={splits.length <= 2}
                  aria-label={t("common.delete")}
                  className="p-2 mb-0.5 rounded-lg hover:bg-rose-500/10 text-rose-400 disabled:opacity-20 transition-all"
                >
                  <Trash2 size={18} />
                </button>
              </div>
            ))}
          </div>

          <button
            onClick={addSplit}
            className="mt-4 flex items-center gap-2 text-[var(--primary)] hover:text-[var(--primary-dark)] text-sm font-semibold transition-all"
          >
            <Plus size={16} /> {t("modals.split.addSplit")}
          </button>
        </div>

        <div className="p-4 md:p-6 border-t border-[var(--surface-light)] bg-[var(--surface-light)]/10 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            {Math.abs(remainingAmount) >= 0.01 ? (
              <div className="flex items-center gap-2 text-amber-400">
                <AlertCircle size={18} />
                <span className="text-sm font-medium">
                  {t("modals.split.remaining")}:{" "}
                  {formatCurrency(remainingAmount, 2)}
                </span>
              </div>
            ) : (
              <div className="text-emerald-400 text-sm font-bold flex items-center gap-2">
                <div className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                {t("modals.split.balanced")}
              </div>
            )}
          </div>

          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-6 py-2 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold transition-all"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={handleSubmit}
              disabled={!isValid}
              className="px-6 py-2 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-dark)] disabled:opacity-50 disabled:cursor-not-allowed text-white text-sm font-semibold shadow-lg shadow-[var(--primary)]/20 transition-all"
            >
              {t("modals.split.title")}
            </button>
          </div>
        </div>
    </Modal>
  );
}
