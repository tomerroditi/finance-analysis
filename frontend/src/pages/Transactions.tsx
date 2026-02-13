import { useQuery } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import { transactionsApi } from "../services/api";
import { useAppStore } from "../stores/appStore";
import { TransactionsTable } from "../components/TransactionsTable";
import { AutoTaggingPanel } from "../components/transactions/AutoTaggingPanel";
import RefundsView from "../components/transactions/RefundsView";
import { pendingRefundsApi } from "../services/api";

import { TransactionFormModal } from "../components/modals/TransactionFormModal";

export function Transactions() {
  const { selectedService, setSelectedService } = useAppStore();
  const [includeSplitParents, setIncludeSplitParents] = useState(false);
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false);

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
      const key = `${pr.source_table}_${pr.source_id}`;
      map.set(key, pr);
    });
    return map;
  }, [pendingRefunds]);

  const refundLinksMap = useMemo(() => {
    const map = new Map<string, number>();
    if (!pendingRefunds) return map;

    pendingRefunds.forEach((pr: any) => {
      if (pr.links) {
        pr.links.forEach((link: any) => {
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
    { value: "manual_investments", label: "Investments" },
    { value: "refunds", label: "Refunds" },
  ] as const;

  return (
    <div className="flex relative">
      <div className="space-y-6 min-w-0 flex-1 transition-all duration-300">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-3xl font-bold">Transactions</h1>
            <p className="text-[var(--text-muted)]">
              View and manage your transactions
            </p>
          </div>

          <div className="flex items-center gap-4">
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
              showSplitParentsFilter
              includeSplitParents={includeSplitParents}
              onIncludeSplitParentsChange={setIncludeSplitParents}
              rowsPerPage={10}
              rowsPerPageOptions={[10, 50, 100, 500, 1000]}
              onTransactionUpdated={refreshAll}
              pendingRefundsMap={pendingRefundsMap}
              refundLinksMap={refundLinksMap}
              onAddTransaction={
                (selectedService === "cash" || selectedService === "manual_investments")
                  ? () => setIsCreateModalOpen(true)
                  : undefined
              }
            />
          )}
        </div>
      </div>

      <AutoTaggingPanel />

      <TransactionFormModal
        isOpen={isCreateModalOpen}
        onClose={() => setIsCreateModalOpen(false)}
        service={
          (selectedService === "cash" || selectedService === "manual_investments")
            ? (selectedService as "cash" | "manual_investments")
            : undefined
        }
        onSuccess={refreshAll}
      />
    </div>
  );
}
