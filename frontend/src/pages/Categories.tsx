import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Wallet } from "lucide-react";
import { taggingApi } from "../services/api";
import { Skeleton } from "../components/common/Skeleton";
import { Modal } from "../components/common/Modal";
import { useCategories } from "../hooks/useCategories";
import { CategoryDetailPanel } from "../components/categories/CategoryDetailPanel";
import { RulesSection } from "../components/categories/RulesSection";

export function Categories() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();

  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [isAddCategoryOpen, setIsAddCategoryOpen] = useState(false);

  const { data: categories, isLoading } = useCategories();
  const { data: icons } = useQuery({
    queryKey: ["category-icons"],
    queryFn: () => taggingApi.getIcons().then((res) => res.data),
  });

  const createCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.createCategory(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddCategoryOpen(false);
    },
  });

  const categoriesRecord = categories as Record<string, string[]> | undefined;

  const filteredEntries = useMemo(() => {
    if (!categoriesRecord) return [];
    const allEntries = Object.entries(categoriesRecord).sort(([a], [b]) => a.localeCompare(b));
    const query = searchQuery.toLowerCase().trim();
    if (!query) return allEntries;
    return allEntries.filter(
      ([category, tags]) =>
        category.toLowerCase().includes(query) ||
        tags.some((tagName) => tagName.toLowerCase().includes(query)),
    );
  }, [categoriesRecord, searchQuery]);

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-8">
        <Skeleton variant="text" lines={2} className="w-full md:w-64" />
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} variant="card" className="h-28" />
          ))}
        </div>
      </div>
    );

  const selectedTags = selectedCategory ? (categoriesRecord?.[selectedCategory] ?? []) : [];

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex items-center justify-end gap-3">
        <button
          onClick={() => setIsAddCategoryOpen(true)}
          className="flex items-center justify-center gap-2 px-4 md:px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold shadow-lg shadow-[var(--primary)]/20 hover:bg-[var(--primary-dark)] transition-all text-sm md:text-base"
        >
          <Plus size={18} /> {t("categories.newCategory")}
        </button>
      </div>

      {/* Search Bar */}
      <div className="relative">
        <Search size={16} className="absolute start-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
        <input
          type="text"
          placeholder={t("categories.searchPlaceholder")}
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl ps-11 pe-4 py-2 text-sm outline-none focus:border-[var(--primary)] transition-all"
        />
      </div>

      {/* Category Grid */}
      {filteredEntries.length > 0 ? (
        <div className="grid grid-cols-4 lg:grid-cols-5 gap-2 sm:gap-3">
          {filteredEntries.map(([category, tags]) => {
            const icon = icons?.[category];
            return (
              <button
                key={category}
                data-testid={`category-card-${category}`}
                onClick={() => setSelectedCategory(category)}
                className="flex flex-col items-center gap-1.5 sm:gap-2 p-2 sm:p-4 bg-[var(--surface)] rounded-xl sm:rounded-2xl border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--surface-light)]/30 transition-all text-center group"
              >
                <div className="w-9 h-9 sm:w-12 sm:h-12 flex items-center justify-center rounded-lg sm:rounded-xl bg-blue-500/10 border border-blue-500/20 text-lg sm:text-2xl shrink-0">
                  {icon ? (
                    <span>{icon}</span>
                  ) : (
                    <Wallet className="text-blue-400 w-[18px] h-[18px] sm:w-[22px] sm:h-[22px]" />
                  )}
                </div>
                <h3 className="font-bold text-xs sm:text-sm truncate w-full" dir="auto">
                  {category}
                </h3>
                <span className="text-[10px] sm:text-xs text-[var(--text-muted)]" dir="ltr">
                  {t("categories.tagsCount", { count: tags.length })}
                </span>
              </button>
            );
          })}
        </div>
      ) : (
        searchQuery.trim() && (
          <div className="text-center py-12 text-[var(--text-muted)]">
            <Search size={40} className="mx-auto mb-3 opacity-30" />
            <p className="font-bold">{t("categories.noResults")}</p>
            <p className="text-sm mt-1">{t("categories.noResultsHint")}</p>
          </div>
        )
      )}

      {/* Auto-Tagging Rules */}
      <div className="pt-2">
        <RulesSection />
      </div>

      {/* Detail Panel */}
      {selectedCategory && (
        <CategoryDetailPanel
          category={selectedCategory}
          tags={selectedTags}
          icon={icons?.[selectedCategory]}
          allCategories={Object.keys(categoriesRecord ?? {})}
          allIcons={icons ?? {}}
          onClose={() => setSelectedCategory(null)}
          onRenameCategory={(newName) => setSelectedCategory(newName)}
        />
      )}

      {/* Create Category Modal */}
      <Modal
        isOpen={isAddCategoryOpen}
        onClose={() => setIsAddCategoryOpen(false)}
        title={t("categories.createNewCategory")}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6">
          <input
            autoFocus
            type="text"
            placeholder={t("categories.categoryName")}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
            onKeyDown={(e) => {
              const val = (e.target as HTMLInputElement).value.trim();
              if (e.key === "Enter" && val) createCategoryMutation.mutate(val);
              if (e.key === "Escape") setIsAddCategoryOpen(false);
            }}
          />
          <div className="flex gap-3">
            <button
              onClick={() => setIsAddCategoryOpen(false)}
              className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={(e) => {
                const val = (
                  e.currentTarget.parentElement?.previousElementSibling as HTMLInputElement
                ).value.trim();
                if (val) createCategoryMutation.mutate(val);
              }}
              className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
            >
              {t("categories.create")}
            </button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
