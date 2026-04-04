import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Shield, ArrowUpRight, ArrowDownRight } from "lucide-react";
import { transactionsApi } from "../services/api";
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

export function Insurances() {
  const { t } = useTranslation();
  const { data: transactions, isLoading } = useQuery({
    queryKey: ["transactions", "insurances"],
    queryFn: () =>
      transactionsApi.getAll("insurances").then((res) => res.data as InsuranceTransaction[]),
  });

  const accounts = transactions
    ? Object.entries(
        transactions.reduce(
          (acc, tx) => {
            const key = tx.account_number || tx.account_name;
            if (!acc[key]) {
              acc[key] = {
                accountNumber: tx.account_number,
                accountName: tx.account_name,
                provider: tx.provider,
                transactions: [],
              };
            }
            acc[key].transactions.push(tx);
            return acc;
          },
          {} as Record<
            string,
            {
              accountNumber: string;
              accountName: string;
              provider: string;
              transactions: InsuranceTransaction[];
            }
          >,
        ),
      ).map(([, v]) => v)
    : [];

  const totalDeposits = transactions
    ?.filter((t) => t.amount > 0)
    .reduce((s, t) => s + t.amount, 0) ?? 0;
  const totalWithdrawals = transactions
    ?.filter((t) => t.amount < 0)
    .reduce((s, t) => s + Math.abs(t.amount), 0) ?? 0;

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
              <p className="text-xl font-black mt-1 text-white">{accounts.length}</p>
            </div>
            <div className="bg-[var(--surface)] rounded-xl p-4 md:p-5 border border-[var(--surface-light)]">
              <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
                Total Deposits
              </p>
              <p className="text-xl font-black mt-1 text-emerald-400">
                {formatCurrency(totalDeposits)}
              </p>
            </div>
            <div className="bg-[var(--surface)] rounded-xl p-4 md:p-5 border border-[var(--surface-light)]">
              <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">
                Total Charges
              </p>
              <p className="text-xl font-black mt-1 text-rose-400">
                {formatCurrency(totalWithdrawals)}
              </p>
            </div>
          </div>

          {/* Per-account sections */}
          {accounts.map((account) => {
            const sorted = [...account.transactions].sort(
              (a, b) => b.date.localeCompare(a.date),
            );
            return (
              <div
                key={account.accountNumber}
                className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden"
              >
                <div className="px-4 md:px-6 py-3 md:py-4 border-b border-[var(--surface-light)] flex items-center justify-between">
                  <div>
                    <h3 className="text-white font-bold">
                      {humanizeProvider(account.provider)} — {account.accountName}
                    </h3>
                    <p className="text-xs text-[var(--text-muted)]">
                      {t("insurance.policy")} {account.accountNumber} · {sorted.length} {t("insurance.transactions")}
                    </p>
                  </div>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--surface-light)]">
                        <th className="text-start px-3 md:px-6 py-3 font-bold">Date</th>
                        <th className="text-start px-3 md:px-6 py-3 font-bold">Description</th>
                        <th className="text-end px-3 md:px-6 py-3 font-bold">Amount</th>
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
