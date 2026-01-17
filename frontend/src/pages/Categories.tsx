import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, MoveRight, Wallet } from "lucide-react";
import { taggingApi } from "../services/api";

const PREDEFINED_EMOJIS = [
  "💰",
  "🍔",
  "🍕",
  "🏠",
  "🚗",
  "🏥",
  "🎓",
  "🎁",
  "🛒",
  "✈️",
  "🎮",
  "📱",
  "👕",
  "🍿",
  "⛽",
  "🚇",
  "🚌",
  "🍷",
  "☕",
  "💼",
  "📈",
  "🏦",
  "💳",
  "💸",
  "🧹",
  "🧴",
  "🐕",
  "🐱",
  "🏋️",
  "🎨",
  "🛠️",
  "💡",
  "🔌",
  "📶",
  "📞",
  "🌴",
  "🎬",
  "🎭",
  "🎤",
  "🎧",
];

export function Categories() {
  const queryClient = useQueryClient();
  const [isAddCategoryOpen, setIsAddCategoryOpen] = useState(false);
  const [isAddTagOpen, setIsAddTagOpen] = useState<{ category: string } | null>(
    null,
  );
  const [isRelocateOpen, setIsRelocateOpen] = useState<{
    category: string;
    tag: string;
  } | null>(null);
  const [editingIcon, setEditingIcon] = useState<{
    category: string;
    currentIcon: string;
  } | null>(null);
  const [tempIcon, setTempIcon] = useState("");

  const { data: categories, isLoading } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

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

  const deleteCategoryMutation = useMutation({
    mutationFn: (name: string) => taggingApi.deleteCategory(name),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["categories"] }),
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
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["categories"] }),
  });

  const relocateTagMutation = useMutation({
    mutationFn: ({ tag, newCategory, oldCategory }: any) =>
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

  if (isLoading)
    return (
      <div className="p-8 text-center text-[var(--text-muted)]">Loading...</div>
    );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Categories & Tags</h1>
          <p className="text-[var(--text-muted)] mt-1">
            Manage your expense classification and tagging logic
          </p>
        </div>
        <button
          onClick={() => setIsAddCategoryOpen(true)}
          className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold shadow-lg shadow-[var(--primary)]/20 hover:bg-[var(--primary-dark)] transition-all"
        >
          <Plus size={18} /> New Category
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
        {categories &&
          Object.entries(categories as Record<string, string[]>).map(
            ([category, tags]) => (
              <div
                key={category}
                className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-6 shadow-sm hover:shadow-xl transition-all flex flex-col"
              >
                <div className="flex items-center justify-between mb-4">
                  <div className="flex items-center gap-3">
                    <button
                      onClick={() => {
                        const currentIcon = icons?.[category] || "💰";
                        setEditingIcon({ category, currentIcon });
                        setTempIcon(currentIcon);
                      }}
                      className="p-2.5 rounded-xl bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all text-xl w-11 h-11 flex items-center justify-center border border-blue-500/20"
                      title="Change Icon"
                    >
                      {icons?.[category] || <Wallet size={20} />}
                    </button>
                    <h3 className="font-bold text-lg text-white">{category}</h3>
                  </div>
                  <button
                    onClick={() => {
                      if (
                        window.confirm(
                          `Delete category "${category}"? All associated tags will be nullified in existing transactions.`,
                        )
                      ) {
                        deleteCategoryMutation.mutate(category);
                      }
                    }}
                    className="p-2 rounded-lg hover:bg-red-500/10 text-[var(--text-muted)] hover:text-red-400 opacity-0 group-hover:opacity-100 transition-all"
                  >
                    <Trash2 size={18} />
                  </button>
                </div>

                <div className="flex-1 space-y-2">
                  <div className="flex flex-wrap gap-2">
                    {tags.map((tag) => (
                      <div
                        key={tag}
                        className="group/tag flex items-center gap-2 px-3 py-1.5 rounded-lg bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 transition-all"
                      >
                        <span className="text-sm font-medium text-[var(--text-muted)]">
                          {tag}
                        </span>
                        <div className="flex items-center gap-0.5 opacity-0 group-hover/tag:opacity-100 transition-all ml-1">
                          <button
                            onClick={() => setIsRelocateOpen({ category, tag })}
                            className="p-1 hover:bg-blue-500/10 text-blue-400 rounded transition-colors"
                            title="Relocate Tag"
                          >
                            <MoveRight size={12} />
                          </button>
                          <button
                            onClick={() => {
                              if (
                                window.confirm(
                                  `Delete tag "${tag}" from "${category}"? It will be removed from all existing transactions.`,
                                )
                              ) {
                                deleteTagMutation.mutate({ category, tag });
                              }
                            }}
                            className="p-1 hover:bg-red-500/10 text-red-400 rounded transition-colors"
                            title="Delete Tag"
                          >
                            <Trash2 size={12} />
                          </button>
                        </div>
                      </div>
                    ))}
                  </div>
                  {tags.length === 0 && (
                    <div className="text-xs text-[var(--text-muted)] italic py-2">
                      No tags defined
                    </div>
                  )}
                </div>

                <button
                  onClick={() => setIsAddTagOpen({ category })}
                  className="mt-6 flex items-center justify-center gap-2 py-2 rounded-xl border border-dashed border-[var(--surface-light)] text-xs font-bold text-[var(--text-muted)] hover:border-[var(--primary)]/50 hover:text-[var(--primary)] transition-all"
                >
                  <Plus size={14} /> Add Tag
                </button>
              </div>
            ),
          )}
      </div>

      {/* Modals */}
      {isAddCategoryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">Create New Category</h3>
            <input
              autoFocus
              type="text"
              placeholder="Category Name"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  createCategoryMutation.mutate(
                    (e.target as HTMLInputElement).value,
                  );
                if (e.key === "Escape") setIsAddCategoryOpen(false);
              }}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setIsAddCategoryOpen(false)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={(e) => {
                  const val = (
                    e.currentTarget.parentElement
                      ?.previousElementSibling as HTMLInputElement
                  ).value;
                  if (val) createCategoryMutation.mutate(val);
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      {isAddTagOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              Add Tag to{" "}
              <span className="text-[var(--primary)]">
                {isAddTagOpen.category}
              </span>
            </h3>
            <input
              autoFocus
              type="text"
              placeholder="Tag Name"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] mb-6 transition-all"
              onKeyDown={(e) => {
                if (e.key === "Enter")
                  createTagMutation.mutate({
                    category: isAddTagOpen.category,
                    tag: (e.target as HTMLInputElement).value,
                  });
                if (e.key === "Escape") setIsAddTagOpen(null);
              }}
            />
            <div className="flex gap-3">
              <button
                onClick={() => setIsAddTagOpen(null)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={(e) => {
                  const val = (
                    e.currentTarget.parentElement
                      ?.previousElementSibling as HTMLInputElement
                  ).value;
                  if (val)
                    createTagMutation.mutate({
                      category: isAddTagOpen.category,
                      tag: val,
                    });
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Add Tag
              </button>
            </div>
          </div>
        </div>
      )}

      {isRelocateOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-sm animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-2">Relocate Tag</h3>
            <p className="text-sm text-[var(--text-muted)] mb-6">
              Move{" "}
              <span className="font-bold text-white">
                "{isRelocateOpen.tag}"
              </span>{" "}
              to a different category
            </p>

            <div className="space-y-2 max-h-[200px] overflow-y-auto mb-6 pr-2">
              {categories &&
                Object.keys(categories)
                  .filter((c) => c !== isRelocateOpen.category)
                  .map((cat) => (
                    <button
                      key={cat}
                      onClick={() =>
                        relocateTagMutation.mutate({
                          tag: isRelocateOpen.tag,
                          oldCategory: isRelocateOpen.category,
                          newCategory: cat,
                        })
                      }
                      className="w-full text-left px-4 py-3 rounded-xl bg-[var(--surface-base)] hover:bg-[var(--primary)]/10 border border-transparent hover:border-[var(--primary)]/30 transition-all font-bold group"
                    >
                      <div className="flex items-center justify-between">
                        <span>{cat}</span>
                        <MoveRight
                          size={16}
                          className="opacity-0 group-hover:opacity-100 transition-all"
                        />
                      </div>
                    </button>
                  ))}
            </div>

            <button
              onClick={() => setIsRelocateOpen(null)}
              className="w-full py-2 text-sm font-bold hover:text-white transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {editingIcon && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl p-6 shadow-2xl w-full max-w-md animate-in zoom-in-95 duration-200">
            <h3 className="text-lg font-bold mb-4">
              Change Icon for{" "}
              <span className="text-[var(--primary)]">
                {editingIcon.category}
              </span>
            </h3>

            <div className="space-y-6">
              {/* Emoji Grid */}
              <div>
                <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
                  Popular Icons
                </p>
                <div className="grid grid-cols-8 gap-2 max-h-[160px] overflow-y-auto p-1">
                  {PREDEFINED_EMOJIS.map((emoji) => (
                    <button
                      key={emoji}
                      onClick={() => setTempIcon(emoji)}
                      className={`w-10 h-10 flex items-center justify-center rounded-lg bg-[var(--surface-base)] border transition-all text-xl ${
                        tempIcon === emoji
                          ? "border-[var(--primary)] bg-[var(--primary)]/20"
                          : "border-[var(--surface-light)] hover:border-[var(--primary)] hover:bg-[var(--primary)]/10"
                      }`}
                    >
                      {emoji}
                    </button>
                  ))}
                </div>
              </div>

              {/* Custom Input */}
              <div>
                <p className="text-xs font-bold text-[var(--text-muted)] uppercase tracking-wider mb-3">
                  Custom Emoji or Text
                </p>
                <input
                  autoFocus
                  type="text"
                  maxLength={4}
                  value={tempIcon}
                  onChange={(e) => setTempIcon(e.target.value)}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-2xl text-center outline-none focus:border-[var(--primary)] transition-all"
                  onKeyDown={(e) => {
                    if (e.key === "Enter")
                      updateIconMutation.mutate({
                        category: editingIcon.category,
                        icon: tempIcon,
                      });
                    if (e.key === "Escape") setEditingIcon(null);
                  }}
                />
              </div>
            </div>

            <div className="flex gap-3 mt-8">
              <button
                onClick={() => setEditingIcon(null)}
                className="flex-1 py-2 text-sm font-bold hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  if (tempIcon)
                    updateIconMutation.mutate({
                      category: editingIcon.category,
                      icon: tempIcon,
                    });
                }}
                className="flex-1 py-2 bg-[var(--primary)] rounded-xl text-white font-bold hover:bg-[var(--primary-dark)] transition-all"
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
