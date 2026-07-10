import type React from "react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Modal } from "../common/Modal";
import { MultiSelect } from "../common/MultiSelect";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategories } from "../../hooks/useCategories";
import { budgetApi, type YearlyAnalysis } from "../../services/api";

interface Props {
  isOpen: boolean;
  onClose: () => void;
  year: number;
  editRule: YearlyAnalysis["rules"][number]["rule"] | null;
}

/**
 * Create/edit modal for yearly budget rules. Stages name/category/tags/amount
 * locally and commits once on Save. Tags are selected via MultiSelect and
 * scoped to the staged category. A 400 conflict from the backend (a tag
 * already used by the monthly budget for this year) is surfaced inline
 * under the Tags field.
 */
export const YearlyRuleModal: React.FC<Props> = ({ isOpen, onClose, year, editRule }) => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { data: categoriesMap } = useCategories();

  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [tags, setTags] = useState<string[]>([]);
  const [amount, setAmount] = useState("");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setName(editRule?.name ?? "");
      setCategory(editRule?.category ?? "");
      setTags(editRule?.tags ?? []);
      setAmount(editRule ? String(editRule.amount) : "");
      setError(null);
    }
  }, [isOpen, editRule]);

  const categories = categoriesMap ? Object.keys(categoriesMap) : [];
  const tagOptions = category && categoriesMap ? (categoriesMap[category] ?? []) : [];

  const mutation = useMutation({
    mutationFn: () => {
      const payload = { name, amount: Number(amount), category, tags, year };
      return editRule
        ? budgetApi.updateYearlyRule(editRule.id, {
            name,
            amount: Number(amount),
            category,
            tags,
          })
        : budgetApi.createYearlyRule(payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["yearlyBudget", year] });
      onClose();
    },
    onError: (err: unknown) => {
      const detail =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ??
        t("budget.yearly.saveFailed");
      setError(detail);
    },
  });

  const canSave = !!name && !!category && tags.length > 0 && !!amount;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={editRule ? t("budget.yearly.editTitle") : t("budget.yearly.addTitle")}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 space-y-4 overflow-y-auto">
        <div>
          <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
            {t("budget.yearly.nameLabel")}
          </label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder={t("budget.yearly.namePlaceholder")}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
          />
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
              {t("budget.yearly.categoryLabel")}
            </label>
            <SelectDropdown
              value={category}
              onChange={(v) => {
                setCategory(v);
                setTags([]);
              }}
              options={categories.map((c) => ({ label: c, value: c }))}
              placeholder={t("budget.yearly.categoryPlaceholder")}
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
              {t("budget.yearly.amountLabel")}
            </label>
            <input
              type="number"
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              placeholder={t("budget.yearly.amountPlaceholder")}
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
            />
          </div>
        </div>

        <div>
          <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
            {t("budget.yearly.tagsLabel")}
          </label>
          <MultiSelect
            options={tagOptions}
            selected={tags}
            onChange={(selected) => {
              setTags(selected);
              setError(null);
            }}
            placeholder={t("budget.yearly.tagsPlaceholder")}
          />
          {error && (
            <p className="text-xs text-red-400 mt-2" dir="auto">
              {error}
            </p>
          )}
        </div>

        <div className="pt-4 flex gap-3 shrink-0">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-3 font-bold text-[var(--text-muted)] hover:text-white transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            type="button"
            onClick={() => {
              setError(null);
              mutation.mutate();
            }}
            disabled={mutation.isPending || !canSave}
            className="flex-1 py-3 bg-[var(--primary)] text-white font-bold rounded-xl hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20 disabled:opacity-50"
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
};
