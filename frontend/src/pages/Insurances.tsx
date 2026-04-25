import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Shield, ArrowUpRight, ArrowDownRight, Pencil, Check, X, RotateCcw } from "lucide-react";
import { insuranceAccountsApi, transactionsApi, type InsuranceAccount } from "../services/api";
import { Skeleton } from "../components/common/Skeleton";
import { humanizeProvider } from "../utils/textFormatting";
import { formatCurrency } from "../utils/numberFormatting";

interface InsuranceTransaction {
  unique_id: number;
  date: string;
  description: string;
  amount: number;
  provider: string;
  account_number: string;
  account_name: string;
  memo?: string;
}

interface AccountGroup {
  policyId: string;
  scrapedName: string;
  provider: string;
  transactions: InsuranceTransaction[];
}

export function Insurances() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const [editingPolicyId, setEditingPolicyId] = useState<string | null>(null);
  const [draftName, setDraftName] = useState("");

  const { data: transactions, isLoading } = useQuery({
    queryKey: ["transactions", "insurances"],
    queryFn: () =>
      transactionsApi.getAll("insurances").then((res) => res.data as InsuranceTransaction[]),
  });

  const { data: insuranceAccounts } = useQuery({
    queryKey: ["insuranceAccounts"],
    queryFn: () => insuranceAccountsApi.getAll().then((res) => res.data),
  });

  const renameMutation = useMutation({
    mutationFn: ({ policyId, customName }: { policyId: string; customName: string | null }) =>
      insuranceAccountsApi.rename(policyId, customName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["insuranceAccounts"] });
      queryClient.invalidateQueries({ queryKey: ["investments"] });
      setEditingPolicyId(null);
      setDraftName("");
    },
  });

  const accountByPolicyId = new Map<string, InsuranceAccount>(
    (insuranceAccounts ?? []).map((a) => [a.policy_id, a]),
  );

  const groups: AccountGroup[] = transactions
    ? Object.values(
        transactions.reduce(
          (acc, tx) => {
            const key = tx.account_number || tx.account_name;
            if (!acc[key]) {
              acc[key] = {
                policyId: tx.account_number,
                scrapedName: tx.account_name,
                provider: tx.provider,
                transactions: [],
              };
            }
            acc[key].transactions.push(tx);
            return acc;
          },
          {} as Record<string, AccountGroup>,
        ),
      )
    : [];

  const totalDeposits = transactions
    ?.filter((tx) => tx.amount > 0)
    .reduce((s, tx) => s + tx.amount, 0) ?? 0;
  const totalWithdrawals = transactions
    ?.filter((tx) => tx.amount < 0)
    .reduce((s, tx) => s + Math.abs(tx.amount), 0) ?? 0;

  const startEditing = (policyId: string, currentName: string) => {
    setEditingPolicyId(policyId);
    setDraftName(currentName);
  };

  const cancelEditing = () => {
    setEditingPolicyId(null);
    setDraftName("");
  };

  const saveName = (policyId: string) => {
    const trimmed = draftName.trim();
    renameMutation.mutate({ policyId, customName: trimmed || null });
  };

  const resetName = (policyId: string) => {
    renameMutation.mutate({ policyId, customName: null });
  };

  return (
    <div className="flex flex-col gap-3 md:gap-6 p-4 md:p-6">
      {isLoading ? (
        <div className="space-y-4">
          <Skeleton className="h-24 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : !transactions || transactions.length === 0 ? (
        <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] p-6 md:p-12 text-center">
          <Shield size={48} className="mx-auto text-[var(--text-muted)] mb-4" />
          <h2 className="text-lg font-bold text-white mb-2">No insurance data yet</h2>
          <p className="text-[var(--text-muted)] text-sm">
            Add an insurance provider in Data Sources and run a scrape to see your
            pension and savings data here.
          </p>
        </div>
      ) : (
        <>
          {/* Summary cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
            <div className="bg-[var(--surface)] rounded-xl p-4 md:p-5 border border-[var(--surface-light)]">
              <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
                Accounts
              </p>
              <p className="text-xl font-black mt-1 text-white">{groups.length}</p>
            </div>
            <div className="bg-[var(--surface)] rounded-xl p-4 md:p-5 border border-[var(--surface-light)]">
              <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
                Total Deposits
              </p>
              <p className="text-xl font-black mt-1 text-emerald-400">
                <span dir="ltr">{formatCurrency(totalDeposits)}</span>
              </p>
            </div>
            <div className="bg-[var(--surface)] rounded-xl p-4 md:p-5 border border-[var(--surface-light)]">
              <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
                Total Charges
              </p>
              <p className="text-xl font-black mt-1 text-rose-400">
                <span dir="ltr">{formatCurrency(totalWithdrawals)}</span>
              </p>
            </div>
          </div>

          {/* Per-account sections */}
          {groups.map((group) => {
            const sorted = [...group.transactions].sort(
              (a, b) => b.date.localeCompare(a.date),
            );
            const account = accountByPolicyId.get(group.policyId);
            const customName = account?.custom_name ?? null;
            const displayName = customName || group.scrapedName;
            const isEditing = editingPolicyId === group.policyId;
            const isSaving = renameMutation.isPending && renameMutation.variables?.policyId === group.policyId;

            return (
              <div
                key={group.policyId}
                className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden"
              >
                <div className="px-4 md:px-6 py-3 md:py-4 border-b border-[var(--surface-light)] flex items-start justify-between gap-3">
                  <div className="min-w-0 flex-1">
                    {isEditing ? (
                      <div className="flex flex-col gap-2">
                        <div className="text-xs text-[var(--text-muted)]">
                          {humanizeProvider(group.provider)} · {t("insurance.policy")} {group.policyId}
                        </div>
                        <div className="flex items-center gap-2 flex-wrap">
                          <input
                            type="text"
                            value={draftName}
                            onChange={(e) => setDraftName(e.target.value)}
                            onKeyDown={(e) => {
                              if (e.key === "Enter") saveName(group.policyId);
                              if (e.key === "Escape") cancelEditing();
                            }}
                            placeholder={group.scrapedName}
                            disabled={isSaving}
                            autoFocus
                            className="flex-1 min-w-[180px] bg-[var(--surface-light)] text-white rounded-lg px-3 py-1.5 text-sm border border-[var(--surface-light)] focus:border-[var(--accent)] outline-none"
                          />
                          <button
                            type="button"
                            onClick={() => saveName(group.policyId)}
                            disabled={isSaving}
                            aria-label={t("insurance.save")}
                            title={t("insurance.save")}
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-50"
                          >
                            <Check size={16} />
                          </button>
                          <button
                            type="button"
                            onClick={cancelEditing}
                            disabled={isSaving}
                            aria-label={t("insurance.cancel")}
                            title={t("insurance.cancel")}
                            className="w-[32px] h-[32px] flex items-center justify-center rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"
                          >
                            <X size={16} />
                          </button>
                          {customName && (
                            <button
                              type="button"
                              onClick={() => resetName(group.policyId)}
                              disabled={isSaving}
                              aria-label={t("insurance.resetToScrapedName")}
                              title={t("insurance.resetToScrapedName")}
                              className="w-[32px] h-[32px] flex items-center justify-center rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"
                            >
                              <RotateCcw size={14} />
                            </button>
                          )}
                        </div>
                        <p className="text-[10px] text-[var(--text-muted)]">
                          {t("insurance.renameFundHint")}
                        </p>
                      </div>
                    ) : (
                      <>
                        <div className="flex items-center gap-2">
                          <h3 className="text-white font-bold truncate">
                            {humanizeProvider(group.provider)} — {displayName}
                          </h3>
                          <button
                            type="button"
                            onClick={() => startEditing(group.policyId, customName ?? "")}
                            aria-label={t("insurance.renameFund")}
                            title={t("insurance.renameFund")}
                            className="shrink-0 w-[32px] h-[32px] flex items-center justify-center rounded-lg text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                          >
                            <Pencil size={14} />
                          </button>
                        </div>
                        <p className="text-xs text-[var(--text-muted)]">
                          {t("insurance.policy")} {group.policyId} · {sorted.length} {t("insurance.transactions")}
                          {customName && (
                            <span className="ms-2 italic">({group.scrapedName})</span>
                          )}
                        </p>
                      </>
                    )}
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full min-w-[480px] text-sm">
                    <thead>
                      <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--surface-light)]">
                        <th className="text-start px-3 md:px-6 py-3 font-bold whitespace-nowrap">Date</th>
                        <th className="text-start px-3 md:px-6 py-3 font-bold">Description</th>
                        <th className="text-end px-3 md:px-6 py-3 font-bold whitespace-nowrap">Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {sorted.map((tx) => (
                        <tr
                          key={tx.unique_id}
                          className="border-b border-[var(--surface-light)]/50 hover:bg-[var(--surface-light)]/30 transition-colors"
                        >
                          <td className="px-3 md:px-6 py-3 text-[var(--text-muted)] whitespace-nowrap">
                            {tx.date}
                          </td>
                          <td className="px-3 md:px-6 py-3 text-white">{tx.description}</td>
                          <td className="px-3 md:px-6 py-3 text-end whitespace-nowrap">
                            <span
                              className={`inline-flex items-center gap-1 font-mono font-bold ${
                                tx.amount >= 0 ? "text-emerald-400" : "text-rose-400"
                              }`}
                              dir="ltr"
                            >
                              {tx.amount >= 0 ? (
                                <ArrowUpRight size={14} />
                              ) : (
                                <ArrowDownRight size={14} />
                              )}
                              {formatCurrency(Math.abs(tx.amount))}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            );
          })}
        </>
      )}
    </div>
  );
}
