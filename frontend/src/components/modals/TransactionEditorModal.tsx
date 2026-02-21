import React, { useState } from "react";
import { X } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { taggingApi, transactionsApi, cashBalancesApi } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";

interface TransactionEditorModalProps {
  transaction: any;
  onClose: () => void;
  onSuccess: () => void;
}

export function TransactionEditorModal({
  transaction,
  onClose,
  onSuccess,
}: TransactionEditorModalProps) {
  const isManual =
    transaction.source?.includes("cash") ||
    transaction.source?.includes("manual_investment");
  const isCash = transaction.source?.includes("cash");

  const [formData, setFormData] = useState({
    date: transaction.date,
    description: transaction.description || transaction.desc || "",
    amount: transaction.amount,
    category: transaction.category || "",
    tag: transaction.tag || "",
    account_name: transaction.account_name || "",
  });

  const { data: categories } = useQuery({
    queryKey: ["categories"],
    queryFn: () => taggingApi.getCategories().then((res) => res.data),
  });

  const { data: cashBalances = [] } = useQuery({
    queryKey: ["cash-balances"],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
    enabled: isCash,
  });

  const availableTags =
    formData.category && categories ? categories[formData.category] || [] : [];

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await transactionsApi.update(transaction.unique_id, {
        ...formData,
        source: transaction.source,
      });
      onSuccess();
      onClose();
    } catch (err) {
      alert("Failed to update transaction.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-2xl shadow-2xl w-full max-w-md overflow-hidden animate-in zoom-in-95 duration-200">
        <div className="px-6 py-4 border-b border-[var(--surface-light)] flex items-center justify-between bg-[var(--surface-light)]/20">
          <h2 className="text-xl font-bold text-white">Edit Transaction</h2>
          <button
            onClick={onClose}
            className="p-1 hover:bg-[var(--surface-light)] rounded-lg transition-colors"
          >
            <X size={20} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="p-6 space-y-4">
          {!isManual && (
            <div className="bg-blue-500/10 border border-blue-500/20 text-blue-400 p-3 rounded-xl text-xs mb-4">
              Note: For bank/credit card transactions, only Category and Tag can
              be modified to maintain data integrity.
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                Date
              </label>
              <input
                type="date"
                disabled={!isManual}
                value={formData.date}
                onChange={(e) =>
                  setFormData({ ...formData, date: e.target.value })
                }
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all font-mono"
              />
            </div>

            {isManual && (
              <div>
                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                  Account / Wallet Name
                </label>
                {isCash ? (
                  <SelectDropdown
                    options={cashBalances.map((b: any) => ({
                      label: b.account_name,
                      value: b.account_name,
                    }))}
                    value={formData.account_name}
                    onChange={(val) =>
                      setFormData({ ...formData, account_name: val })
                    }
                    placeholder="Select an Envelope"
                  />
                ) : (
                  <input
                    type="text"
                    value={formData.account_name}
                    onChange={(e) =>
                      setFormData({ ...formData, account_name: e.target.value })
                    }
                    className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] transition-all"
                  />
                )}
              </div>
            )}

            <div>
              <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                Description
              </label>
              <input
                type="text"
                disabled={!isManual}
                value={formData.description}
                onChange={(e) =>
                  setFormData({ ...formData, description: e.target.value })
                }
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                Amount
              </label>
              <div className="relative">
                <span className="absolute left-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)] text-sm">
                  ₪
                </span>
                <input
                  type="number"
                  step="0.01"
                  disabled={!isManual}
                  value={formData.amount}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      amount: parseFloat(e.target.value),
                    })
                  }
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl pl-10 pr-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all font-mono"
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4 pt-2 border-t border-[var(--surface-light)] mt-4">
              <div>
                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                  Category
                </label>
                <select
                  value={formData.category}
                  onChange={(e) =>
                    setFormData({
                      ...formData,
                      category: e.target.value,
                      tag: "",
                    })
                  }
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] transition-all"
                >
                  <option value="">Select Category</option>
                  {categories &&
                    Object.keys(categories).map((cat) => (
                      <option key={cat} value={cat}>
                        {cat}
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ml-1">
                  Tag
                </label>
                <select
                  value={formData.tag}
                  onChange={(e) =>
                    setFormData({ ...formData, tag: e.target.value })
                  }
                  disabled={!formData.category}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all"
                >
                  <option value="">Select Tag</option>
                  {availableTags.map((tag: string) => (
                    <option key={tag} value={tag}>
                      {tag}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>

          <div className="flex gap-3 mt-8">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 px-4 py-2.5 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold transition-all"
            >
              Cancel
            </button>
            <button
              type="submit"
              className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-dark)] text-white text-sm font-semibold shadow-lg shadow-[var(--primary)]/20 transition-all"
            >
              Save Changes
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
