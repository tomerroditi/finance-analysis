import { useState, useMemo } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Trash2, MoveRight, Wallet, Search,
  ChevronDown, ChevronRight, ChevronsUpDown, Tags, Hash, Pencil,
} from "lucide-react";
import { taggingApi } from "../services/api";
import { Skeleton } from "../components/common/Skeleton";
import { Modal } from "../components/common/Modal";
import { useCategories } from "../hooks/useCategories";
import { IconPickerModal } from "../components/categories/IconPickerModal";

const PROTECTED_CATEGORIES = ["Credit Cards", "Salary", "Other Income", "Investments", "Ignore", "Liabilities"];
const PROTECTED_TAGS = ["Prior Wealth"];

export function Categories() {
  const { t, i18n } = useTranslation();
  const isRtl = i18n.language === "he";
  const queryClient = useQueryClient();

  // UI state
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedCategories, setExpandedCategories] = useState<Set<string>>(new Set());
  const [isAddCategoryOpen, setIsAddCategoryOpen] = useState(false);
  const [isAddTagOpen, setIsAddTagOpen] = useState<{ category: string } | null>(null);
  const [isRelocateOpen, setIsRelocateOpen] = useState<{ category: string; tag: string } | null>(null);
  const [editingIcon, setEditingIcon] = useState<{ category: string; currentIcon: string } | null>(null);
  const [editingCategory, setEditingCategory] = useState<string | null>(null);
  const [editingTag, setEditingTag] = useState<{ category: string; tag: string } | null>(null);
  const [editName, setEditName] = useState("");

  // Data fetching
  const { data: categories, isLoading } = useCategories();
  const { data: icons } = useQuery({
    queryKey: ["category-icons"],
    queryFn: () => taggingApi.getIcons().then((res) => res.data),
  });

  // Mutations
  const createCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.createCategory(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddCategoryOpen(false);
    },
  });

  const deleteCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.deleteCategory(name),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const createTagMutation = useMutation({
    mutationFn: ({ category, tag }: { category: string; tag: string }) =>
      taggingApi.createTag(category, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddTagOpen(null);
    },
  });

  const deleteTagMutation = useMutation({
    mutationFn: ({ category, tag }: { category: string; tag: string }) =>
      taggingApi.deleteTag(category, tag),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const relocateTagMutation = useMutation({
    mutationFn: ({ tag, newCategory, oldCategory }: { tag: string; newCategory: string; oldCategory: string }) =>
      taggingApi.relocateTag(oldCategory, newCategory, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsRelocateOpen(null);
    },
  });

  const updateIconMutation = useMutation({
    mutationFn: ({ category, icon }: { category: string; icon: string }) =>
      taggingApi.updateIcon(category, icon),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["category-icons"] });
      setEditingIcon(null);
    },
  });

  const renameCategoryMutation = useMutation({
    mutationFn: ({ oldName, newName }: { oldName: string; newName: string }) =>
      taggingApi.renameCategory(oldName, newName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      queryClient.invalidateQueries({ queryKey: ["category-icons"] });
      setEditingCategory(null);
    },
    onError: () => {
      alert(t("categories.renameError"));
    },
  });

  const renameTagMutation = useMutation({
    mutationFn: ({ category, oldTag, newTag }: { category: string; oldTag: string; newTag: string }) =>
      taggingApi.renameTag(category, oldTag, newTag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setEditingTag(null);
    },
    onError: () => {
      alert(t("categories.renameError"));
    },
  });

  // Computed values
  const categoriesRecord = categories as Record<string, string[]> | undefined;

  const { filteredEntries, totalTags, matchingTagsByCategory } = useMemo(() => {
    if (!categoriesRecord) return { filteredEntries: [], totalTags: 0, matchingTagsByCategory: new Map<string, Set<string>>() };

    const allEntries = Object.entries(categoriesRecord).sort(([a], [b]) => a.localeCompare(b));
    const total = allEntries.reduce((sum, [, tags]) => sum + tags.length, 0);
    const query = searchQuery.toLowerCase().trim();

    if (!query) {
      return { filteredEntries: allEntries, totalTags: total, matchingTagsByCategory: new Map() };
    }

    const matchingTags = new Map<string, Set<string>>();
    const filtered = allEntries.filter(([category, tags]) => {
      const categoryMatches = category.toLowerCase().includes(query);
      const matchedTags = tags.filter((tagName) => tagName.toLowerCase().includes(query));
      if (matchedTags.length > 0) {
        matchingTags.set(category, new Set(matchedTags));
      }
      return categoryMatches || matchedTags.length > 0;
    });

    return { filteredEntries: filtered, totalTags: total, matchingTagsByCategory: matchingTags };
  }, [categoriesRecord, searchQuery]);

  // Actions
  const toggleCategory = (category: string) => {
    setExpandedCategories((prev) => {
      const next = new Set(prev);
      if (next.has(category)) next.delete(category);
      else next.add(category);
      return next;
    });
  };

  const toggleAll = () => {
    if (!categoriesRecord) return;
    const allKeys = Object.keys(categoriesRecord);
    const allExpanded = allKeys.every((k) => expandedCategories.has(k));
    setExpandedCategories(allExpanded ? new Set() : new Set(allKeys));
  };

  const isCategoryExpanded = (category: string) => {
    if (searchQuery.trim()) return true;
    return expandedCategories.has(category);
  };

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-8">
        <Skeleton variant="text" lines={2} className="w-full md:w-64" />
        <div className="space-y-3">
          <Skeleton variant="card" className="h-16" />
          <Skeleton variant="card" className="h-16" />
          <Skeleton variant="card" className="h-16" />
          <Skeleton variant="card" className="h-16" />
          <Skeleton variant="card" className="h-16" />
        </div>
      </div>
    );

  return (
    <div className="space-y-4 md:space-y-6 animate-in fade-in duration-500">
      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">{t("categories.title")}</h1>
          <p className="text-sm text-[var(--text-muted)] mt-1">{t("categories.subtitle")}</p>
        </div>
        <button
          onClick={() => setIsAddCategoryOpen(true)}
          className="flex items-center justify-center gap-2 px-4 md:px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold shadow-lg shadow-[var(--primary)]/20 hover:bg-[var(--primary-dark)] transition-all text-sm md:text-base"
        >
          <Plus size={18} /> {t("categories.newCategory")}
        </button>
      </div>

      {/* Stats + Search Bar */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Stats */}
        <div className="flex gap-2 shrink-0">
          <div className="flex items-center gap-2 px-3 py-2 bg-[var(--surface)] rounded-xl border border-[var(--surface-light)]">
            <Tags size={14} className="text-[var(--primary)]" />
            <span className="text-xs font-bold text-[var(--text-muted)]">
              {t("categories.categoriesCount", { count: filteredEntries.length })}
            </span>
          </div>
          <div className="flex items-center gap-2 px-3 py-2 bg-[var(--surface)] rounded-xl border border-[var(--surface-light)]">
            <Hash size={14} className="text-[var(--secondary)]" />
            <span className="text-xs font-bold text-[var(--text-muted)]">
              {t("categories.tagsCount", { count: totalTags })}
            </span>
          </div>
        </div>

        {/* Search */}
        <div className="relative flex-1">
          <Search size={16} className="absolute inset-inline-start-3 top-1/2 -translate-y-1/2 text-[var(--text-muted)]" />
          <input
            type="text"
            placeholder={t("categories.searchPlaceholder")}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl ps-9 pe-4 py-2 text-sm outline-none focus:border-[var(--primary)] transition-all"
          />
        </div>

        {/* Expand/Collapse All */}
        {!searchQuery.trim() && (
          <button
            onClick={toggleAll}
            className="flex items-center justify-center gap-2 px-3 py-2 rounded-xl border border-[var(--surface-light)] bg-[var(--surface)] hover:bg-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] hover:text-white transition-all shrink-0"
          >
            <ChevronsUpDown size={14} />
            <span className="hidden sm:inline">{t("categories.toggleAll")}</span>
          </button>
        )}
      </div>

      {/* Category List */}
      <div className="space-y-2">
        {filteredEntries.map(([category, tags]) => {
          const isExpanded = isCategoryExpanded(category);
          const isProtected = PROTECTED_CATEGORIES.includes(category);
          const tagCount = tags.length;
          const icon = icons?.[category];
          const highlightedTags = matchingTagsByCategory.get(category);

          return (
            <div
              key={category}
              className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden transition-all hover:shadow-md"
            >
              {/* Category Header Row */}
              <div className="group flex items-center gap-2 md:gap-3 px-3 md:px-5 py-3 md:py-4 cursor-pointer" onClick={() => toggleCategory(category)}>
                {/* Expand/Collapse Arrow */}
                <span className="text-[var(--text-muted)] shrink-0 transition-transform">
                  {isExpanded
                    ? <ChevronDown size={16} />
                    : isRtl ? <ChevronRight size={16} className="rotate-180" /> : <ChevronRight size={16} />
                  }
                </span>

                {/* Icon */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    setEditingIcon({ category, currentIcon: icon || "💰" });
                  }}
                  className="p-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all text-lg w-9 h-9 md:w-10 md:h-10 flex items-center justify-center border border-blue-500/20 shrink-0"
                  title={t("categories.changeIcon")}
                >
                  {icon || <Wallet size={18} />}
                </button>

                {/* Category Name */}
                <div className="flex-1 min-w-0">
                  {editingCategory === category ? (
                    <input
                      autoFocus
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && editName.trim()) {
                          renameCategoryMutation.mutate({ oldName: category, newName: editName });
                        }
                        if (e.key === "Escape") setEditingCategory(null);
                      }}
                      onBlur={() => setEditingCategory(null)}
                      onClick={(e) => e.stopPropagation()}
                      className="font-bold text-base md:text-lg bg-transparent border-b border-[var(--primary)] outline-none w-full"
                    />
                  ) : (
                    <h3 className="font-bold text-sm md:text-base truncate text-white">
                      {category}
                    </h3>
                  )}
                </div>

                {/* Tag Count Badge */}
                <span className="px-2 py-0.5 rounded-full bg-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] shrink-0" dir="ltr">
                  {tagCount}
                </span>

                {/* Action Buttons - Desktop hover reveal */}
                <div className="hidden md:flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
                  {!isProtected && (
                    <button
                      onClick={() => { setEditingCategory(category); setEditName(category); }}
                      className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 transition-colors"
                      title={t("categories.renameCategory")}
                    >
                      <Pencil size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => setIsAddTagOpen({ category })}
                    className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 transition-colors"
                    title={t("categories.addTag")}
                  >
                    <Plus size={16} />
                  </button>
                  <button
                    onClick={() => {
                      if (!isProtected && window.confirm(t("categories.confirmDeleteCategory", { name: category }))) {
                        deleteCategoryMutation.mutate(category);
                      }
                    }}
                    disabled={isProtected}
                    className={`p-2 rounded-lg transition-colors ${isProtected ? "text-[var(--surface-light)] cursor-not-allowed" : "hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400"}`}
                    title={isProtected ? t("categories.protectedCannotRename") : t("categories.deleteCategory")}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>

                {/* Action Buttons - Mobile always visible */}
                <div className="md:hidden flex items-center gap-1" onClick={(e) => e.stopPropagation()}>
                  {!isProtected && (
                    <button
                      onClick={() => { setEditingCategory(category); setEditName(category); }}
                      className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 transition-colors"
                      title={t("categories.renameCategory")}
                    >
                      <Pencil size={14} />
                    </button>
                  )}
                  <button
                    onClick={() => setIsAddTagOpen({ category })}
                    className="p-2 rounded-lg hover:bg-blue-500/10 text-[var(--text-muted)] hover:text-blue-400 transition-colors"
                    title={t("categories.addTag")}
                  >
                    <Plus size={16} />
                  </button>
                  <button
                    onClick={() => {
                      if (!isProtected && window.confirm(t("categories.confirmDeleteCategory", { name: category }))) {
                        deleteCategoryMutation.mutate(category);
                      }
                    }}
                    disabled={isProtected}
                    className={`p-2 rounded-lg transition-colors ${isProtected ? "text-[var(--surface-light)] cursor-not-allowed" : "hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400"}`}
                    title={isProtected ? t("categories.protectedCannotRename") : t("categories.deleteCategory")}
                  >
                    <Trash2 size={16} />
                  </button>
                </div>
              </div>

              {/* Expanded Tags Section */}
              {isExpanded && (
                <div className="px-3 md:px-5 pb-3 md:pb-4 border-t border-[var(--surface-light)]/50">
                  {tags.length > 0 ? (
                    <div className="flex flex-wrap gap-2 pt-3">
                      {tags.map((tagName) => {
                        const isHighlighted = highlightedTags?.has(tagName);
                        const isTagProtected = PROTECTED_TAGS.includes(tagName);

                        return (
                          <div
                            key={tagName}
                            className={`group/tag flex items-center gap-1.5 px-3 py-1.5 rounded-lg border transition-all ${
                              isHighlighted
                                ? "bg-[var(--primary)]/10 border-[var(--primary)]/30"
                                : "bg-[var(--surface-base)] border-[var(--surface-light)] hover:border-[var(--primary)]/50"
                            }`}
                          >
                            {editingTag?.category === category && editingTag?.tag === tagName ? (
                              <input
                                autoFocus
                                type="text"
                                value={editName}
                                onChange={(e) => setEditName(e.target.value)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter" && editName.trim()) {
                                    renameTagMutation.mutate({ category, oldTag: tagName, newTag: editName });
                                  }
                                  if (e.key === "Escape") setEditingTag(null);
                                }}
                                onBlur={() => setEditingTag(null)}
                                className="text-sm font-medium bg-transparent border-b border-[var(--primary)] outline-none w-20"
                              />
                            ) : (
                              <span
                                className={`text-sm font-medium ${isTagProtected ? "text-[var(--text-muted)]" : "text-[var(--text-muted)] cursor-pointer hover:text-[var(--primary)] transition-colors"}`}
                                onClick={() => {
                                  if (!isTagProtected) {
                                    setEditingTag({ category, tag: tagName });
                                    setEditName(tagName);
                                  }
                                }}
                                title={isTagProtected ? t("categories.protectedCannotRename") : t("categories.renameTag")}
                              >
                                {tagName}
                              </span>
                            )}
                            <div className="flex items-center gap-0.5 opacity-100 md:opacity-0 group-hover/tag:opacity-100 transition-all ms-1">
                              <button
                                onClick={() => setIsRelocateOpen({ category, tag: tagName })}
                                className="p-1 hover:bg-blue-500/10 text-blue-400 rounded transition-colors"
                                title={t("categories.relocateTag")}
                              >
                                <MoveRight size={12} />
                              </button>
                              <button
                                onClick={() => {
                                  if (window.confirm(t("categories.confirmDeleteTag", { tag: tagName, category }))) {
                                    deleteTagMutation.mutate({ category, tag: tagName });
                                  }
                                }}
                                className="p-1 hover:bg-red-500/10 text-red-400 rounded transition-colors"
                                title={t("categories.deleteTag")}
                              >
                                <Trash2 size={12} />
                              </button>
                            </div>
                          </div>
                        );
                      })}

                      {/* Inline Add Tag button */}
                      <button
                        onClick={() => setIsAddTagOpen({ category })}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] hover:border-[var(--primary)]/50 hover:text-[var(--primary)] transition-all"
                      >
                        <Plus size={12} /> {t("categories.addTag")}
                      </button>
                    </div>
                  ) : (
                    <div className="flex items-center gap-3 pt-3">
                      <span className="text-xs text-[var(--text-muted)] italic">
                        {t("categories.noTags")}
                      </span>
                      <button
                        onClick={() => setIsAddTagOpen({ category })}
                        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-dashed border-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] hover:border-[var(--primary)]/50 hover:text-[var(--primary)] transition-all"
                      >
                        <Plus size={12} /> {t("categories.addTag")}
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}

        {filteredEntries.length === 0 && searchQuery.trim() && (
          <div className="text-center py-12 text-[var(--text-muted)]">
            <Search size={40} className="mx-auto mb-3 opacity-30" />
            <p className="font-bold">{t("categories.noResults")}</p>
            <p className="text-sm mt-1">{t("categories.noResultsHint")}</p>
          </div>
        )}
      </div>

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
              if (e.key === "Enter") createCategoryMutation.mutate((e.target as HTMLInputElement).value);
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
                const val = (e.currentTarget.parentElement?.previousElementSibling as HTMLInputElement).value;
                if (val) createCategoryMutation.mutate(val);
              }}
              className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
            >
              {t("categories.create")}
            </button>
          </div>
        </div>
      </Modal>

      {/* Add Tag Modal */}
      <Modal
        isOpen={!!isAddTagOpen}
        onClose={() => setIsAddTagOpen(null)}
        title={`${t("categories.addTagTo")} ${isAddTagOpen?.category ?? ""}`}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6">
          <input
            autoFocus
            type="text"
            placeholder={t("categories.tagName")}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
            onKeyDown={(e) => {
              if (e.key === "Enter" && isAddTagOpen)
                createTagMutation.mutate({ category: isAddTagOpen.category, tag: (e.target as HTMLInputElement).value });
              if (e.key === "Escape") setIsAddTagOpen(null);
            }}
          />
          <div className="flex gap-3">
            <button
              onClick={() => setIsAddTagOpen(null)}
              className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={(e) => {
                const val = (e.currentTarget.parentElement?.previousElementSibling as HTMLInputElement).value;
                if (val && isAddTagOpen)
                  createTagMutation.mutate({ category: isAddTagOpen.category, tag: val });
              }}
              className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
            >
              {t("categories.addTag")}
            </button>
          </div>
        </div>
      </Modal>

      {/* Relocate Tag Modal */}
      <Modal
        isOpen={!!isRelocateOpen}
        onClose={() => setIsRelocateOpen(null)}
        title={t("categories.relocateTag")}
        maxWidth="sm"
      >
        <div className="p-4 md:p-6">
          <p className="text-sm text-[var(--text-muted)] mb-4">
            {t("categories.moveTagDescription", { tag: isRelocateOpen?.tag })}
          </p>
          <div className="space-y-2 max-h-[200px] overflow-y-auto mb-4 pe-2">
            {categories &&
              Object.keys(categories)
                .filter((c) => c !== isRelocateOpen?.category)
                .sort((a, b) => a.localeCompare(b))
                .map((cat) => (
                  <button
                    key={cat}
                    onClick={() =>
                      isRelocateOpen && relocateTagMutation.mutate({
                        tag: isRelocateOpen.tag,
                        oldCategory: isRelocateOpen.category,
                        newCategory: cat,
                      })
                    }
                    className="w-full text-start px-4 py-3 rounded-xl bg-[var(--surface-base)] hover:bg-[var(--primary)]/10 border border-transparent hover:border-[var(--primary)]/30 transition-all font-bold group"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-lg">{icons?.[cat] || "📁"}</span>
                        <span>{cat}</span>
                      </div>
                      <MoveRight
                        size={16}
                        className="opacity-100 md:opacity-0 group-hover:opacity-100 transition-all"
                      />
                    </div>
                  </button>
                ))}
          </div>
          <button
            onClick={() => setIsRelocateOpen(null)}
            className="w-full py-2 text-sm font-bold hover:text-white transition-colors"
          >
            {t("common.cancel")}
          </button>
        </div>
      </Modal>

      {/* Icon Picker Modal */}
      {editingIcon && (
        <IconPickerModal
          isOpen={!!editingIcon}
          onClose={() => setEditingIcon(null)}
          category={editingIcon.category}
          currentIcon={editingIcon.currentIcon}
          onSave={(icon) => updateIconMutation.mutate({ category: editingIcon.category, icon })}
        />
      )}
    </div>
  );
}
