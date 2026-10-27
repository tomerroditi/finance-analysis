import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Plus, Trash2, MoveRight, Wallet } from "lucide-react";
import { taggingApi } from "../../services/api";
import { Modal } from "../common/Modal";
import { IconPickerModal } from "./IconPickerModal";
import { useScrollLock } from "../../hooks/useScrollLock";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { PROTECTED_CATEGORIES, PROTECTED_TAGS } from "./constants";
import { qkPrefix } from "../../services/queryKeys";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import type { RefreshPlan } from "../../queryInvalidation";
import { PendingButton, SavingSpinner } from "../common/PendingButton";

/**
 * What a category/tag delete, move or rename cannot reach: the app's
 * configuration and account balances. It rewrites transactions, rules,
 * budgets and goals by name (`services/tagging_service.py`) — and a tag
 * rename investments and liabilities too — so everything else refreshes.
 * Cash balances are stored sums the tagging writes never recompute.
 */
const CATEGORY_EDIT_SKIP = [
  qkPrefix.credentialsAccounts,
  qkPrefix.providers,
  qkPrefix.backups,
  qkPrefix.lastScrapes,
  ["rates"],
  ["updateCheck"],
  ["versionInfo"],
  qkPrefix.bankBalances,
  qkPrefix.insuranceAccounts,
  qkPrefix.cashBalances,
];

/** The categories map first (and the icons, for a rename), then the rest. */
const editPlan = (withIcons = false): { refresh: RefreshPlan } => ({
  refresh: {
    first: withIcons ? [qkPrefix.categories, qkPrefix.categoryIcons] : [qkPrefix.categories],
    skip: CATEGORY_EDIT_SKIP,
  },
});

interface CategoryDetailPanelProps {
  category: string;
  tags: string[];
  icon: string | undefined;
  allCategories: string[];
  allIcons: Record<string, string>;
  onClose: () => void;
  onRenameCategory: (newName: string) => void;
}

export function CategoryDetailPanel({
  category,
  tags,
  icon,
  allCategories,
  allIcons,
  onClose,
  onRenameCategory,
}: CategoryDetailPanelProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { createTag } = useCategoryTagCreate();
  const confirm = useConfirm();
  const notify = useNotify();
  const isProtected = PROTECTED_CATEGORIES.includes(category);
  const deleteReasonId = useId();

  useScrollLock(true);

  const [isAddTagOpen, setIsAddTagOpen] = useState(false);
  const [isRelocateOpen, setIsRelocateOpen] = useState<string | null>(null);
  const [isIconPickerOpen, setIsIconPickerOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState(false);
  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  // Each write refreshes along a plan the mutation cache follows (none of
  // them invalidates on its own, and none returns a promise for TanStack to
  // await).
  const deleteCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.deleteCategory(name),
    onMutate: () => editPlan(),
    onSuccess: () => onClose(),
  });

  // A new tag lands in the map at once; only the map and its usage refetch.
  const addTag = (tag: string) => {
    createTag(category, tag).then(
      () => setIsAddTagOpen(false),
      () => notify.error(t("categories.tagChangeError")),
    );
  };

  const deleteTagMutation = useMutation({
    mutationFn: ({ tag }: { tag: string }) => taggingApi.deleteTag(category, tag),
    onMutate: () => editPlan(),
    onError: () => notify.error(t("categories.tagChangeError")),
  });

  const relocateTagMutation = useMutation({
    mutationFn: ({ tag, newCategory }: { tag: string; newCategory: string }) =>
      taggingApi.relocateTag(category, newCategory, tag),
    onMutate: () => editPlan(),
    onSuccess: () => setIsRelocateOpen(null),
    onError: () => notify.error(t("categories.tagChangeError")),
  });

  // An icon is read only by the icon map: patch it now, refetch nothing else.
  const updateIconMutation = useMutation({
    mutationFn: ({ icon: newIcon }: { icon: string }) => taggingApi.updateIcon(category, newIcon),
    onMutate: async ({ icon: newIcon }) => {
      await queryClient.cancelQueries({ queryKey: qkPrefix.categoryIcons });
      const before = queryClient.getQueriesData<Record<string, string>>({
        queryKey: qkPrefix.categoryIcons,
      });
      for (const [key, icons] of before) {
        if (icons) queryClient.setQueryData(key, { ...icons, [category]: newIcon });
      }
      return {
        refresh: { only: [qkPrefix.categoryIcons] },
        restore: () => before.forEach(([key, icons]) => queryClient.setQueryData(key, icons)),
      };
    },
    onSuccess: () => setIsIconPickerOpen(false),
    onError: (_error, _variables, context) => context?.restore(),
  });

  const renameCategoryMutation = useMutation({
    mutationFn: ({ newName }: { newName: string }) =>
      taggingApi.renameCategory(category, newName),
    onMutate: () => editPlan(true),
    onSuccess: (_, { newName }) => {
      setEditingCategory(false);
      onRenameCategory(newName);
    },
    onError: () => notify.error(t("categories.renameError")),
  });

  const renameTagMutation = useMutation({
    mutationFn: ({ oldTag, newTag }: { oldTag: string; newTag: string }) =>
      taggingApi.renameTag(category, oldTag, newTag),
    onMutate: () => editPlan(),
    onSuccess: () => setEditingTag(null),
    onError: () => notify.error(t("categories.renameError")),
  });

  const otherCategories = allCategories
    .filter((c) => c !== category)
    .sort((a, b) => a.localeCompare(b));

  return (
    <>
      <div
        className="modal-overlay fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 flex items-center justify-center"
        onClick={onClose}
      >
        <div
          data-testid="category-panel"
          className="relative bg-[var(--surface)] border border-[var(--surface-light)] shadow-2xl flex flex-col max-h-[90vh] w-full max-w-[calc(100vw-2rem)] sm:max-w-md rounded-2xl overflow-hidden animate-in zoom-in-95 duration-200"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Panel header */}
          <div className="px-5 py-4 border-b border-[var(--surface-light)] flex items-center gap-3 bg-[var(--surface-light)]/20 shrink-0">
            <button
              onClick={() => setIsIconPickerOpen(true)}
              className="p-2 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all text-lg w-10 h-10 flex items-center justify-center border border-blue-500/20 shrink-0"
              title={t("categories.changeIcon")}
            >
              {icon || <Wallet size={18} />}
            </button>
            <div className="flex-1 min-w-0">
              {editingCategory ? (
                <div className="flex items-center gap-2">
                  <input
                    autoFocus
                    type="text"
                    value={editName}
                    readOnly={renameCategoryMutation.isPending}
                    aria-busy={renameCategoryMutation.isPending || undefined}
                    onChange={(e) => setEditName(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && editName.trim() && !renameCategoryMutation.isPending) {
                        renameCategoryMutation.mutate({ newName: editName.trim() });
                      }
                      if (e.key === "Escape") setEditingCategory(false);
                    }}
                    onBlur={() => {
                      if (!renameCategoryMutation.isPending) setEditingCategory(false);
                    }}
                    className="font-bold text-xl bg-transparent border-b border-[var(--primary)] outline-none w-full"
                  />
                  {renameCategoryMutation.isPending && <SavingSpinner size={18} />}
                </div>
              ) : (
                <h2
                  className={`font-bold text-xl truncate ${!isProtected ? "cursor-pointer hover:text-[var(--primary)] transition-colors" : ""}`}
                  dir="auto"
                  onClick={() => {
                    if (isProtected) return;
                    setEditingCategory(true);
                    setEditName(category);
                  }}
                  title={!isProtected ? t("categories.renameCategory") : undefined}
                >
                  {category}
                </h2>
              )}
            </div>
            <button
              onClick={onClose}
              aria-label={t("common.close")}
              className="p-2 hover:bg-[var(--surface-light)] rounded-lg transition-colors text-[var(--text-muted)] hover:text-white shrink-0"
            >
              <X size={20} />
            </button>
          </div>

          {/* Panel body */}
          <div className="flex-1 overflow-y-auto p-5 space-y-5">
            {/* Tags section */}
            <div>
              <div className="flex items-center justify-between mb-3">
                <span
                  className="text-xs font-bold uppercase tracking-wider text-[var(--text-muted)]"
                  dir="ltr"
                >
                  {t("categories.tagsCount", { count: tags.length })}
                </span>
                <button
                  onClick={() => setIsAddTagOpen(true)}
                  className="flex items-center gap-1 text-xs font-bold text-[var(--primary)] hover:text-[var(--primary-dark)] transition-colors"
                  title={t("categories.addTag")}
                >
                  <Plus size={12} /> {t("categories.addTag")}
                </button>
              </div>

              {tags.length > 0 ? (
                <div className="flex flex-wrap gap-2">
                  {tags.map((tagName) => {
                    const isTagProtected = PROTECTED_TAGS.includes(tagName);
                    return (
                      <div
                        key={tagName}
                        className="group/tag flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[var(--surface-light)] bg-[var(--surface-base)] hover:border-[var(--primary)]/50 transition-all"
                      >
                        {editingTag === tagName ? (
                          <>
                            <input
                              autoFocus
                              type="text"
                              value={editName}
                              readOnly={renameTagMutation.isPending}
                              aria-busy={renameTagMutation.isPending || undefined}
                              onChange={(e) => setEditName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && editName.trim() && !renameTagMutation.isPending) {
                                  renameTagMutation.mutate({
                                    oldTag: tagName,
                                    newTag: editName.trim(),
                                  });
                                }
                                if (e.key === "Escape") setEditingTag(null);
                              }}
                              onBlur={() => {
                                if (!renameTagMutation.isPending) setEditingTag(null);
                              }}
                              className="text-sm font-medium bg-transparent border-b border-[var(--primary)] outline-none w-20"
                            />
                            {renameTagMutation.isPending && <SavingSpinner size={12} />}
                          </>
                        ) : (
                          <span
                            className={`text-sm font-medium ${
                              isTagProtected
                                ? "text-[var(--text-muted)]"
                                : "text-[var(--text-muted)] cursor-pointer hover:text-[var(--primary)] transition-colors"
                            }`}
                            onClick={() => {
                              if (!isTagProtected) {
                                setEditingTag(tagName);
                                setEditName(tagName);
                              }
                            }}
                            title={
                              isTagProtected
                                ? t("categories.protectedCannotRename")
                                : t("categories.renameTag")
                            }
                            dir="auto"
                          >
                            {tagName}
                          </span>
                        )}
                        <div className="flex items-center gap-0.5 opacity-100 md:opacity-0 group-hover/tag:opacity-100 transition-all ms-1">
                          <button
                            onClick={() => setIsRelocateOpen(tagName)}
                            className="p-1 hover:bg-blue-500/10 text-blue-400 rounded transition-colors"
                            title={t("categories.relocateTag")}
                          >
                            <MoveRight size={12} className="rtl:-scale-x-100" />
                          </button>
                          <PendingButton
                            pending={deleteTagMutation.isPending && deleteTagMutation.variables?.tag === tagName}
                            onClick={async () => {
                              const ok = await confirm({
                                title: t("categories.deleteTag"),
                                message: t("categories.confirmDeleteTag", {
                                  tag: tagName,
                                  category,
                                }),
                                confirmLabel: t("common.delete"),
                                isDestructive: true,
                              });
                              if (ok) deleteTagMutation.mutate({ tag: tagName });
                            }}
                            disabled={isTagProtected}
                            className={`p-1 rounded transition-colors ${
                              isTagProtected
                                ? "opacity-30 cursor-not-allowed text-[var(--text-muted)]"
                                : "hover:bg-red-500/10 text-red-400"
                            }`}
                            title={t("categories.deleteTag")}
                            icon={<Trash2 size={12} />}
                            spinnerSize={12}
                          />
                        </div>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <p className="text-sm text-[var(--text-muted)] italic">
                  {t("categories.noTags")}
                </p>
              )}
            </div>

            {/* Category danger zone */}
            <div className="pt-4 border-t border-[var(--surface-light)]">
              <div className="group relative">
                <PendingButton
                  pending={deleteCategoryMutation.isPending}
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("categories.deleteCategory"),
                      message: t("categories.confirmDeleteCategory", { name: category }),
                      confirmLabel: t("common.delete"),
                      isDestructive: true,
                    });
                    if (ok) deleteCategoryMutation.mutate(category);
                  }}
                  disabled={isProtected}
                  aria-describedby={isProtected ? deleteReasonId : undefined}
                  className={`w-full flex items-center gap-3 px-4 py-3 rounded-xl border border-transparent transition-all font-bold text-sm ${
                    isProtected
                      ? "text-[var(--text-muted)] opacity-50 cursor-not-allowed"
                      : "text-red-400 hover:bg-red-500/10 hover:border-red-500/20"
                  }`}
                  icon={<Trash2 size={16} />}
                  spinnerSize={16}
                >
                  {t("categories.deleteCategory")}
                </PendingButton>
                {isProtected && (
                  <div className="pointer-events-none absolute bottom-full inset-x-0 mb-2 flex justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                    <span
                      id={deleteReasonId}
                      role="tooltip"
                      className="px-3 py-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--surface-light)] text-xs text-[var(--text-muted)] shadow-lg max-w-[calc(100%-1rem)] text-center"
                    >
                      {t("categories.protectedCannotDelete")}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sub-modals rendered outside the panel div */}
      <Modal
        isOpen={isAddTagOpen}
        onClose={() => setIsAddTagOpen(false)}
        title={t("categories.addTagTo", { category })}
        maxWidth="sm"
        zIndex="z-[60]"
      >
        <div className="p-4 md:p-6">
          <input
            autoFocus
            type="text"
            placeholder={t("categories.tagName")}
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
            onKeyDown={(e) => {
              const val = (e.target as HTMLInputElement).value.trim();
              if (e.key === "Enter" && val) addTag(val);
              if (e.key === "Escape") setIsAddTagOpen(false);
            }}
          />
          <div className="flex gap-3">
            <button
              onClick={() => setIsAddTagOpen(false)}
              className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
            >
              {t("common.cancel")}
            </button>
            <button
              onClick={(e) => {
                const val = (
                  e.currentTarget.parentElement?.previousElementSibling as HTMLInputElement
                ).value.trim();
                if (val) addTag(val);
              }}
              className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
            >
              {t("categories.addTag")}
            </button>
          </div>
        </div>
      </Modal>

      <Modal
        isOpen={!!isRelocateOpen}
        onClose={() => setIsRelocateOpen(null)}
        title={t("categories.relocateTag")}
        maxWidth="sm"
        zIndex="z-[60]"
      >
        <div className="p-4 md:p-6">
          <p className="text-sm text-[var(--text-muted)] mb-4">
            {t("categories.moveTagDescription", { tag: isRelocateOpen })}
          </p>
          <div className="space-y-2 max-h-[200px] overflow-y-auto mb-4 pe-2">
            {otherCategories.map((cat) => (
              <PendingButton
                key={cat}
                pending={relocateTagMutation.isPending && relocateTagMutation.variables?.newCategory === cat}
                ownSpinner
                disabled={relocateTagMutation.isPending}
                onClick={() =>
                  isRelocateOpen &&
                  relocateTagMutation.mutate({ tag: isRelocateOpen, newCategory: cat })
                }
                className="w-full text-start px-4 py-3 rounded-xl bg-[var(--surface-base)] hover:bg-[var(--primary)]/10 border border-transparent hover:border-[var(--primary)]/30 transition-all font-bold group"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{allIcons[cat] || "📁"}</span>
                    <span>{cat}</span>
                  </div>
                  {relocateTagMutation.isPending && relocateTagMutation.variables?.newCategory === cat ? (
                    <SavingSpinner size={16} />
                  ) : (
                    <MoveRight
                      size={16}
                      className="opacity-100 md:opacity-0 group-hover:opacity-100 transition-all rtl:-scale-x-100"
                    />
                  )}
                </div>
              </PendingButton>
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

      {isIconPickerOpen && (
        <IconPickerModal
          isOpen={isIconPickerOpen}
          onClose={() => setIsIconPickerOpen(false)}
          category={category}
          currentIcon={icon || "💰"}
          onSave={(newIcon) => updateIconMutation.mutate({ icon: newIcon })}
          zIndex="z-[60]"
        />
      )}
    </>
  );
}
