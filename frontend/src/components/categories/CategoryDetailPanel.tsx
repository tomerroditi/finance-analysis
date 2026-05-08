import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { X, Plus, Trash2, MoveRight, Wallet } from "lucide-react";
import { taggingApi } from "../../services/api";
import { Modal } from "../common/Modal";
import { IconPickerModal } from "./IconPickerModal";
import { useScrollLock } from "../../hooks/useScrollLock";
import { useConfirm, useNotify } from "../../context/DialogContext";
import { PROTECTED_CATEGORIES, PROTECTED_TAGS } from "./constants";

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
  const confirm = useConfirm();
  const notify = useNotify();
  const isProtected = PROTECTED_CATEGORIES.includes(category);

  useScrollLock(true);

  const [isAddTagOpen, setIsAddTagOpen] = useState(false);
  const [isRelocateOpen, setIsRelocateOpen] = useState<string | null>(null);
  const [isIconPickerOpen, setIsIconPickerOpen] = useState(false);
  const [editingCategory, setEditingCategory] = useState(false);
  const [editingTag, setEditingTag] = useState<string | null>(null);
  const [editName, setEditName] = useState("");

  const deleteCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.deleteCategory(name),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      onClose();
    },
  });

  const createTagMutation = useMutation({
    mutationFn: ({ tag }: { tag: string }) => taggingApi.createTag(category, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsAddTagOpen(false);
    },
  });

  const deleteTagMutation = useMutation({
    mutationFn: ({ tag }: { tag: string }) => taggingApi.deleteTag(category, tag),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const relocateTagMutation = useMutation({
    mutationFn: ({ tag, newCategory }: { tag: string; newCategory: string }) =>
      taggingApi.relocateTag(category, newCategory, tag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setIsRelocateOpen(null);
    },
  });

  const updateIconMutation = useMutation({
    mutationFn: ({ icon: newIcon }: { icon: string }) => taggingApi.updateIcon(category, newIcon),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["category-icons"] });
      setIsIconPickerOpen(false);
    },
  });

  const renameCategoryMutation = useMutation({
    mutationFn: ({ newName }: { newName: string }) =>
      taggingApi.renameCategory(category, newName),
    onSuccess: (_, { newName }) => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      queryClient.invalidateQueries({ queryKey: ["category-icons"] });
      setEditingCategory(false);
      onRenameCategory(newName);
    },
    onError: () => notify.error(t("categories.renameError")),
  });

  const renameTagMutation = useMutation({
    mutationFn: ({ oldTag, newTag }: { oldTag: string; newTag: string }) =>
      taggingApi.renameTag(category, oldTag, newTag),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["categories"] });
      setEditingTag(null);
    },
    onError: () => notify.error(t("categories.renameError")),
  });

  const otherCategories = allCategories
    .filter((c) => c !== category)
    .sort((a, b) => a.localeCompare(b));

  return (
    <>
      <div
        className="modal-overlay fixed inset-0 z-50 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200 flex items-center justify-center md:items-stretch md:justify-end"
        onClick={onClose}
      >
        <div
          data-testid="category-panel"
          className="relative bg-[var(--surface)] border border-[var(--surface-light)] md:border-e-0 md:border-y-0 md:border-s shadow-2xl flex flex-col max-h-[90vh] md:max-h-none md:h-full w-full max-w-[calc(100vw-2rem)] sm:max-w-md md:w-[420px] rounded-2xl md:rounded-none md:rounded-s-2xl overflow-hidden animate-in zoom-in-95 duration-200"
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
                <input
                  autoFocus
                  type="text"
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && editName.trim()) {
                      renameCategoryMutation.mutate({ newName: editName.trim() });
                    }
                    if (e.key === "Escape") setEditingCategory(false);
                  }}
                  onBlur={() => setEditingCategory(false)}
                  className="font-bold text-xl bg-transparent border-b border-[var(--primary)] outline-none w-full"
                />
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
                          <input
                            autoFocus
                            type="text"
                            value={editName}
                            onChange={(e) => setEditName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter" && editName.trim()) {
                                renameTagMutation.mutate({
                                  oldTag: tagName,
                                  newTag: editName.trim(),
                                });
                              }
                              if (e.key === "Escape") setEditingTag(null);
                            }}
                            onBlur={() => setEditingTag(null)}
                            className="text-sm font-medium bg-transparent border-b border-[var(--primary)] outline-none w-20"
                          />
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
                            <MoveRight size={12} />
                          </button>
                          <button
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
                          >
                            <Trash2 size={12} />
                          </button>
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
            {!isProtected && (
              <div className="pt-4 border-t border-[var(--surface-light)]">
                <button
                  onClick={async () => {
                    const ok = await confirm({
                      title: t("categories.deleteCategory"),
                      message: t("categories.confirmDeleteCategory", { name: category }),
                      confirmLabel: t("common.delete"),
                      isDestructive: true,
                    });
                    if (ok) deleteCategoryMutation.mutate(category);
                  }}
                  className="w-full flex items-center gap-3 px-4 py-3 rounded-xl text-red-400 hover:bg-red-500/10 border border-transparent hover:border-red-500/20 transition-all font-bold text-sm"
                >
                  <Trash2 size={16} />
                  {t("categories.deleteCategory")}
                </button>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Sub-modals rendered outside the panel div */}
      <Modal
        isOpen={isAddTagOpen}
        onClose={() => setIsAddTagOpen(false)}
        title={`${t("categories.addTagTo")} ${category}`}
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
              if (e.key === "Enter" && val) createTagMutation.mutate({ tag: val });
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
                if (val) createTagMutation.mutate({ tag: val });
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
              <button
                key={cat}
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
