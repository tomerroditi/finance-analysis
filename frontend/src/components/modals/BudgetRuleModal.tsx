import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { taggingApi } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useScrollLock } from "../../hooks/useScrollLock";

interface BudgetRuleModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (rule: object) => void;
  initialData?: { id: number; name: string; amount: number; category: string; tags?: string | string[] } | null;
  selectedYear: number;
  selectedMonth: number;
}

export function BudgetRuleModal({
  isOpen,
  onClose,
  onSave,
  initialData,
  selectedYear,
  selectedMonth,
}: BudgetRuleModalProps) {
  const { t } = useTranslation();
  const { createCategory } = useCategoryTagCreate();
  useScrollLock(isOpen);
  const [name, setName] = useState("");
  const [amount, setAmount] = useState("");
  const [category, setCategory] = useState("");
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Fetch categories for dropdown
  const { data: categoriesMap } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const categories = categoriesMap ? Object.keys(categoriesMap) : [];
  const availableTags =
    category && categoriesMap && (categoriesMap as Record<string, string[]>)[category]
      ? (categoriesMap as Record<string, string[]>)[category]
      : [];

  useEffect(() => {
    if (isOpen) {
      if (initialData) {
        setName(initialData.name);
        setAmount(initialData.amount.toString());
        setCategory(initialData.category);

        // Handle tags as array or string
        let parsedTags: string[] = [];
        if (Array.isArray(initialData.tags)) {
          parsedTags = initialData.tags;
        } else if (typeof initialData.tags === "string") {
          parsedTags = initialData.tags
            .split(";")
            .map((t: string) => t.trim())
            .filter((t: string) => t !== "");
        }
        setSelectedTags(parsedTags);
      } else {
        // New rule defaults
        setName("");
        setAmount("");
        setCategory("");
        setSelectedTags([]);
      }
    }
  }, [isOpen, initialData]);

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSave({
        name,
        amount: parseFloat(amount),
        category,
        tags: selectedTags, // Send as array, budget_service handles conversion
        year: selectedYear === 0 ? null : selectedYear,
        month: selectedMonth === 0 ? null : selectedMonth,
      });
      onClose();
    } catch (error) {
      console.error("Failed to save budget rule", error);
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isOpen) return null;

  const isProjectRule = selectedYear === 0;

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-md shadow-2xl animate-in zoom-in-95 duration-200 h-fit max-h-[90vh] flex flex-col">
        <div className="flex items-center justify-between p-4 md:p-6 border-b border-[var(--surface-light)] shrink-0">
          <h2 className="text-lg md:text-xl font-bold">
            {initialData
              ? isProjectRule
                ? `${t("modals.budgetRule.editRule")}: ${category} - ${Array.isArray(initialData.tags) ? initialData.tags.join(", ") : initialData.tags}`
                : t("modals.budgetRule.editRule")
              : t("modals.budgetRule.addRule")}
          </h2>
          <button
            onClick={onClose}
            className="p-2 hover:bg-[var(--surface-light)] rounded-full transition-colors"
          >
            <X size={20} className="text-[var(--text-muted)]" />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-4 md:p-6 space-y-4 overflow-y-auto">
          <div>
            <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
              {t("modals.budgetRule.ruleName")}
            </label>
            <input
              type="text"
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t("modals.budgetRule.ruleNamePlaceholder")}
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50"
              disabled={isProjectRule && !!initialData}
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
              {t("common.amount")} (ILS)
            </label>
            <input
              type="number"
              required
              min="0"
              step="0.01"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
            />
          </div>

          <div>
            <label className="block text-xs font-bold uppercase text-[var(--text-muted)] mb-1.5">
              {t("common.category")}
            </label>
            <SelectDropdown
              options={categories.map((c: string) => ({ label: c, value: c }))}
              value={category}
              onChange={(val) => {
                setCategory(val);
                if (categoriesMap && (categoriesMap as Record<string, string[]>)[val]) {
                  setSelectedTags((categoriesMap as Record<string, string[]>)[val]);
                } else {
                  setSelectedTags([]);
                }
              }}
              placeholder={t("modals.transactionForm.selectCategory")}
              required
              disabled={isProjectRule && !!initialData}
              onCreateNew={async (name) => {
                const formatted = await createCategory(name);
                setCategory(formatted);
                setSelectedTags([]);
              }}
            />
          </div>

          <div>
            <div className="flex justify-between items-center mb-1.5">
              <label className="block text-xs font-bold uppercase text-[var(--text-muted)]">
                {t("modals.budgetRule.tags")}
              </label>
              {availableTags.length > 0 && !isProjectRule && (
                <button
                  type="button"
                  onClick={() => {
                    if (selectedTags.length === availableTags.length) {
                      setSelectedTags([]);
                    } else {
                      setSelectedTags([...(availableTags as string[])]);
                    }
                  }}
                  className="text-xs text-[var(--primary)] hover:underline font-medium"
                >
                  {selectedTags.length === availableTags.length
                    ? t("modals.budgetRule.deselectAll")
                    : t("modals.budgetRule.selectAll")}
                </button>
              )}
            </div>
            {isProjectRule && !!initialData ? (
              <input
                type="text"
                value={selectedTags.join(", ")}
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none font-medium disabled:opacity-50"
                disabled
              />
            ) : (
              <div className="bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl p-3 max-h-48 overflow-y-auto space-y-2">
                {availableTags.length > 0 ? (
                  <div className="flex flex-wrap gap-2">
                    {(availableTags as string[]).map((tag) => (
                      <button
                        key={tag}
                        type="button"
                        onClick={() => handleTagToggle(tag)}
                        className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${
                          selectedTags.includes(tag)
                            ? "bg-[var(--primary)] text-white shadow-sm"
                            : "bg-[var(--surface-light)] text-[var(--text-muted)] hover:bg-[var(--surface-base)] border border-transparent hover:border-[var(--surface-light)]"
                        }`}
                      >
                        {tag}
                      </button>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-[var(--text-muted)] italic">
                    {category
                      ? t("modals.budgetRule.noTagsForCategory")
                      : t("modals.budgetRule.selectCategoryFirst")}
                  </p>
                )}
              </div>
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
              type="submit"
              disabled={isSubmitting}
              className="flex-1 py-3 bg-[var(--primary)] text-white font-bold rounded-xl hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20 disabled:opacity-50"
            >
              {isSubmitting ? t("modals.budgetRule.saving") : t("modals.budgetRule.saveRule")}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
