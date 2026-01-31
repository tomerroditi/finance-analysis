import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { ShieldCheck } from "lucide-react";
import { transactionsApi } from "../services/api";
import { useAppStore } from "../stores/appStore";
import { TransactionsTable } from "../components/TransactionsTable";
import { RuleManager } from "../components/modals/RuleManager";
import RefundsView from "../components/transactions/RefundsView";
import { pendingRefundsApi } from "../services/api";

export function Transactions() {
  const { selectedService, setSelectedService } = useAppStore();
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [showRuleManager, setShowRuleManager] = useState(false);

  // Clean up any potential import artifacts if I messed up previously

  const {
    data: transactions,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ["transactions", selectedService, includeSplitParents],
    queryFn: () =>
      transactionsApi
        .getAll(
          selectedService === "all" ? undefined : selectedService,
          includeSplitParents,
        )
        .then((res) => res.data),
    enabled: selectedService !== "refunds",
  });

  // Fetch pending refunds to know which transactions are already marked
  const { data: pendingRefunds, refetch: refetchPending } = useQuery({
    queryKey: ["pendingRefunds", "all"],
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  // Create a map of pending refunds by source ID for quick lookup
  const pendingRefundsMap = useMemo(() => {
    const map = new Map<string, any>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr) => {
      // Key format matches default getTransactionId: `${source}_${unique_id}`
      // Adjust based on your ID strategy. Here we use source_table and source_id.
      // Note: TransactionTable uses `${source}_${unique_id}` or source from API.
      // API returns source like 'banks', 'credit_cards' etc.
      // Pending refund object has source_table and source_id.
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  // Create a map of Transactions that are linked to pending refunds (i.e. they ARE the refund)
  // map: transaction_id (string key) -> link_id (number)
  const refundLinksMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      if (pr.links) {
        pr.links.forEach((link: any) => {
          // Key format: source_table + val (which is unique_id usually)
          // Wait, getTransactionId uses tx.source and tx.unique_id
          // Link has refund_source and refund_transaction_id.
          const key = `${link.refund_source}_${link.refund_transaction_id}`;
          map.set(key, link.id);
        });
      }
    });
    return map;
  }, [pendingRefunds]);

  // Refetch both when actions happen
  const refreshAll = () => {
    refetch();
    refetchPending();
  };

  const services = [
    { value: "all", label: "All" },
    { value: "credit_cards", label: "Credit Card" },
    { value: "banks", label: "Bank" },
    { value: "cash", label: "Cash" },
    { value: "refunds", label: "Refunds" },
  ] as const;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Transactions</h1>
          <div className="flex items-center gap-4 mt-1">
            <p className="text-[var(--text-muted)]">
              View and manage your transactions
            </p>
            {selectedService !== "refunds" && (
              <>
                <div className="flex items-center gap-2 px-3 py-1 bg-[var(--surface-light)]/20 rounded-full border border-[var(--surface-light)]">
                  <label
                    className="text-xs font-medium text-[var(--text-muted)] cursor-pointer select-none"
                    htmlFor="split-parents"
                  >
                    Show Split Parents
                  </label>
                  <input
                    id="split-parents"
                    type="checkbox"
                    checked={includeSplitParents}
                    onChange={(e) => setIncludeSplitParents(e.target.checked)}
                    className="w-3 h-3 rounded border-slate-700 bg-slate-800 text-blue-500 focus:ring-blue-500 cursor-pointer"
                  />
                </div>
              </>
            )}
          </div>
        </div>

        <div className="flex items-center gap-4">
          <button
            onClick={() => setShowRuleManager(true)}
            className="px-4 py-2 rounded-lg bg-[var(--surface)] border border-[var(--surface-light)] text-sm font-semibold hover:border-[var(--primary)] transition-all flex items-center gap-2"
          >
            <ShieldCheck size={16} className="text-[var(--primary)]" /> Rules
          </button>

          <div className="w-px h-8 bg-[var(--surface-light)] mx-2" />

          <div className="flex gap-2 items-center">
            {services.map(({ value, label }) => (
              <div key={value} className="flex items-center gap-2">
                {value === "refunds" && (
                  <div className="w-px h-6 bg-[var(--surface-light)] mx-1" />
                )}
                <button
                  onClick={() => setSelectedService(value as any)}
                  className={`px-4 py-2 rounded-lg transition-colors ${selectedService === value
                    ? "bg-[var(--primary)] text-white"
                    : "bg-[var(--surface)] text-[var(--text-muted)] hover:bg-[var(--surface-light)]"
                    }`}
                >
                  {label}
                </button>
              </div>
            ))}
          </div>
        </div>
      </div>

      <div className="bg-[var(--surface)] rounded-xl border border-[var(--surface-light)] overflow-hidden p-4">
        {selectedService === "refunds" ? (
          <RefundsView />
        ) : isLoading ? (
          <div className="p-8 text-center text-[var(--text-muted)]">
            Loading...
          </div>
        ) : (
          <TransactionsTable
            transactions={transactions || []}
            showSelection
            showBulkActions
            showActions
            showDelete
            showFilter
            rowsPerPage={10} // Default rows per page
            rowsPerPageOptions={[10, 50, 100, 500, 1000]}
            onTransactionUpdated={refreshAll}
            pendingRefundsMap={pendingRefundsMap}
            refundLinksMap={refundLinksMap}
          />
        )}
      </div>

      {showRuleManager && (
        <RuleManager onClose={() => setShowRuleManager(false)} />
      )}
    </div>
  );
}
