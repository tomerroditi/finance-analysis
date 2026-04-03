import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { transactionsApi } from "../../services/api";
import { SelectDropdown } from "../common/SelectDropdown";
import { useCategoryTagCreate } from "../../hooks/useCategoryTagCreate";
import { useCategories } from "../../hooks/useCategories";
import { useCashBalances } from "../../hooks/useCashBalances";
import { Modal } from "../common/Modal";
import type { Transaction } from "../../types/transaction";

export type { Transaction };

interface TransactionFormModalProps {
    isOpen: boolean;
    onClose: () => void;
    transaction?: Transaction | null; // If provided, we are in Edit mode
    service?: "cash" | "manual_investments"; // Required if creating new
    onSuccess: () => void;
}

export function TransactionFormModal({
    isOpen,
    onClose,
    transaction,
    service,
    onSuccess,
}: TransactionFormModalProps) {
    const { t } = useTranslation();
    const isEditMode = !!transaction;

    // If editing, check if it's a manual transaction (cash/investments)
    // If creating, it's always manual (we only allow creating manual txs)
    const isManual = isEditMode
        ? transaction?.source?.includes("cash") ||
        transaction?.source?.includes("manual_investment")
        : true; // Creating is always manual

    const [formData, setFormData] = useState({
        date: new Date().toISOString().split("T")[0],
        description: "",
        amount: 0,
        category: "",
        tag: "",
        account_name: "", // Required for creation
    });

    const [transactionType, setTransactionType] = useState<"expense" | "income">("expense");

    // Load initial data when opening
     
    useEffect(() => {
        if (isOpen && transaction) {
            // eslint-disable-next-line react-hooks/set-state-in-effect
            setFormData({
                date: transaction.date,
                description: transaction.description || transaction.desc || "",
                amount: Math.abs(transaction.amount), // specific logic for display
                category: transaction.category || "",
                tag: transaction.tag || "",
                account_name: transaction.account_name || "",
            });
            setTransactionType(transaction.amount >= 0 ? "income" : "expense");
        } else if (isOpen) {
            // Reset for create mode
            setFormData({
                date: new Date().toISOString().split("T")[0],
                description: "",
                amount: 0,
                category: "",
                tag: "",
                account_name: "",
            });
            setTransactionType("expense");
        }
    }, [isOpen, transaction]);

    const { createCategory, createTag } = useCategoryTagCreate();

    const { data: categories } = useCategories({ enabled: isOpen });

    // Fetch cash balances (envelopes) for cash transactions (both new and edit)
    const isCashTransaction = (!isEditMode && service === "cash") ||
                               (isEditMode && transaction?.source?.includes("cash"));
    const { data: cashBalances = [] } = useCashBalances({ enabled: isOpen && isCashTransaction });

    const availableTags =
        formData.category && categories ? categories[formData.category] || [] : [];

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();

        // Calculate final amount based on type override users manual input sign
        const finalAmount = transactionType === "expense"
            ? -Math.abs(formData.amount)
            : Math.abs(formData.amount);

        try {
            if (isEditMode && transaction) {
                await transactionsApi.update(transaction.unique_id || "", {
                    ...formData,
                    amount: isManual ? finalAmount : transaction.amount, // Only update amount if manual, else keep original
                    source: transaction.source, // Backend needs source for routing updates
                });
            } else {
                if (!service) {
                    alert("Service (Cash/Investments) is required for new transactions");
                    return;
                }
                await transactionsApi.create({
                    ...formData,
                    amount: finalAmount,
                    service: service, // "cash" or "manual_investments"
                    provider: "MANUAL",
                });
            }
            onSuccess();
            onClose();
        } catch (err) {
            console.error(err);
            alert("Failed to save transaction.");
        }
    };

    return (
        <Modal
            isOpen={isOpen}
            onClose={onClose}
            title={isEditMode ? t("modals.transactionForm.editTitle") : t("modals.transactionForm.addTitle")}
            titleId="transaction-form-title"
        >
                <form onSubmit={handleSubmit} className="p-4 md:p-6 space-y-4 overflow-y-auto">
                    {isEditMode && !isManual && (
                        <div className="bg-blue-500/10 border border-blue-500/20 text-blue-400 p-3 rounded-xl text-xs mb-4">
                            {t("modals.transactionForm.readOnlyNote")}
                        </div>
                    )}

                    <div className="space-y-4">
                        {/* Date */}
                        <div>
                            <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                {t("common.date")}
                            </label>
                            <input
                                type="date"
                                disabled={isEditMode && !isManual}
                                value={formData.date}
                                onChange={(e) =>
                                    setFormData({ ...formData, date: e.target.value })
                                }
                                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all font-mono"
                                required
                            />
                        </div>

                        {/* Account Name - Shown only on Create or if Manual Edit */}
                        {(isManual) && (
                            <div>
                                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                    {t("modals.transactionForm.accountName")}
                                </label>
                                {isCashTransaction ? (
                                    <SelectDropdown
                                        options={cashBalances.map((b: { account_name: string }) => ({
                                            label: b.account_name,
                                            value: b.account_name,
                                        }))}
                                        value={formData.account_name}
                                        onChange={(val) =>
                                            setFormData({ ...formData, account_name: val })
                                        }
                                        placeholder={t("modals.transactionForm.selectEnvelope")}
                                        required
                                    />
                                ) : (
                                    <input
                                        type="text"
                                        value={formData.account_name}
                                        onChange={(e) =>
                                            setFormData({ ...formData, account_name: e.target.value })
                                        }
                                        placeholder={t("modals.transactionForm.accountPlaceholder")}
                                        className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all"
                                        required
                                    />
                                )}
                            </div>
                        )}

                        {/* Description */}
                        <div>
                            <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                {t("common.description")}
                            </label>
                            <input
                                type="text"
                                disabled={isEditMode && !isManual}
                                value={formData.description}
                                onChange={(e) =>
                                    setFormData({ ...formData, description: e.target.value })
                                }
                                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all"
                                required
                            />
                        </div>

                        {/* Amount and Type */}
                        <div>
                            <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                {t("common.amount")}
                            </label>
                            <div className="flex gap-2">
                                {isManual && (
                                    <div className="flex bg-[var(--surface-base)] rounded-xl border border-[var(--surface-light)] p-1">
                                        <button
                                            type="button"
                                            onClick={() => setTransactionType("expense")}
                                            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${transactionType === "expense" ? "bg-red-500/20 text-red-500" : "text-[var(--text-muted)] hover:text-[var(--text-default)]"}`}
                                        >
                                            {t("modals.transactionForm.expense")}
                                        </button>
                                        <button
                                            type="button"
                                            onClick={() => setTransactionType("income")}
                                            className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-all ${transactionType === "income" ? "bg-emerald-500/20 text-emerald-500" : "text-[var(--text-muted)] hover:text-[var(--text-default)]"}`}
                                        >
                                            {t("modals.transactionForm.income")}
                                        </button>
                                    </div>
                                )}
                                <div className="relative flex-1">
                                    <span className="absolute start-4 top-1/2 -translate-y-1/2 text-[var(--text-muted)] text-sm">
                                        ₪
                                    </span>
                                    <input
                                        type="number"
                                        step="0.01"
                                        min="0"
                                        disabled={isEditMode && !isManual}
                                        value={formData.amount}
                                        onChange={(e) =>
                                            setFormData({
                                                ...formData,
                                                amount: parseFloat(e.target.value),
                                            })
                                        }
                                        className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl ps-10 pe-4 py-2.5 text-sm outline-none focus:border-[var(--primary)] disabled:opacity-50 transition-all font-mono"
                                        required
                                    />
                                </div>
                            </div>
                        </div>

                        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2 border-t border-[var(--surface-light)] mt-4">
                            <div>
                                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                    {t("common.category")}
                                </label>
                                <SelectDropdown
                                    options={categories ? Object.keys(categories).map((cat) => ({ label: cat, value: cat })) : []}
                                    value={formData.category}
                                    onChange={(val) =>
                                        setFormData({
                                            ...formData,
                                            category: val,
                                            tag: "",
                                        })
                                    }
                                    placeholder={t("modals.transactionForm.selectCategory")}
                                    onCreateNew={async (name) => {
                                        const formatted = await createCategory(name);
                                        setFormData({ ...formData, category: formatted, tag: "" });
                                    }}
                                />
                            </div>

                            <div>
                                <label className="block text-xs font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-1.5 ms-1">
                                    {t("common.tag")}
                                </label>
                                <SelectDropdown
                                    options={availableTags.map((tag: string) => ({ label: tag, value: tag }))}
                                    value={formData.tag}
                                    onChange={(val) =>
                                        setFormData({ ...formData, tag: val })
                                    }
                                    placeholder={t("modals.transactionForm.selectTag")}
                                    disabled={!formData.category}
                                    onCreateNew={async (name) => {
                                        const formatted = await createTag(formData.category, name);
                                        setFormData({ ...formData, tag: formatted });
                                    }}
                                />
                            </div>
                        </div>
                    </div>

                    <div className="flex gap-3 mt-8">
                        <button
                            type="button"
                            onClick={onClose}
                            className="flex-1 px-4 py-2.5 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold transition-all"
                        >
                            {t("common.cancel")}
                        </button>
                        <button
                            type="submit"
                            className="flex-1 px-4 py-2.5 rounded-xl bg-[var(--primary)] hover:bg-[var(--primary-dark)] text-white text-sm font-semibold shadow-lg shadow-[var(--primary)]/20 transition-all"
                        >
                            {isEditMode ? t("modals.transactionForm.saveChanges") : t("modals.transactionForm.createTransaction")}
                        </button>
                    </div>
                </form>
        </Modal>
    );
}
