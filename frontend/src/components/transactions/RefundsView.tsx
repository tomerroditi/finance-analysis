import React, { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowLeftRight,
  CheckCircle2,
  CircleDashed,
  Link,
  Calendar,
  CreditCard,
} from "lucide-react";
import { pendingRefundsApi, type PendingRefund } from "../../services/api";

const RefundsView: React.FC = () => {
  const { data: refunds, isLoading } = useQuery({
    queryKey: ["pendingRefunds", "all"],
    queryFn: () => pendingRefundsApi.getAll().then((res) => res.data),
  });

  const groupedRefunds = useMemo(() => {
    if (!refunds) return { active: [], resolved: [] };

    // Group by status, but keep partial in pending for now or separate?
    // Let's separate resolved from active (pending/partial)
    const active = refunds.filter((r) => r.status !== "resolved");
    const resolved = refunds.filter((r) => r.status === "resolved");

    // Sort by date desc (if date available)
    const sorter = (a: PendingRefund, b: PendingRefund) => {
      const da = a.date ? new Date(a.date).getTime() : 0;
      const db = b.date ? new Date(b.date).getTime() : 0;
      return db - da; // Descending
    };

    return {
      active: active.sort(sorter),
      resolved: resolved.sort(sorter),
    };
  }, [refunds]);

  const formatCurrency = (amount: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(amount);

  if (isLoading) {
    return (
      <div className="p-8 text-center text-[var(--text-muted)]">
        Loading refunds...
      </div>
    );
  }

  const renderRefundCard = (item: PendingRefund) => (
    <div
      key={item.id}
      className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl overflow-hidden mb-4"
    >
      {/* Header: The Source Expense */}
      <div className="p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 bg-[var(--surface-light)]/30">
        <div className="flex items-start gap-4">
          <div
            className={`p-2 rounded-lg ${item.status === "resolved" ? "bg-emerald-500/10 text-emerald-500" : "bg-amber-500/10 text-amber-500"}`}
          >
            {item.status === "resolved" ? (
              <CheckCircle2 size={20} />
            ) : (
              <CircleDashed size={20} />
            )}
          </div>
          <div>
            <div className="flex items-center gap-2 mb-1">
              <span className="font-semibold text-lg">
                {item.description || "Unknown Expense"}
              </span>
              <span className="text-xs px-2 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)] uppercase">
                {item.provider || item.source_table}
              </span>
            </div>
            <div className="flex items-center gap-4 text-sm text-[var(--text-muted)]">
              <span className="flex items-center gap-1">
                <Calendar size={14} />
                {item.date || "No date"}
              </span>
              <span className="flex items-center gap-1">
                <CreditCard size={14} />
                {item.account_name || "Unknown Account"}
              </span>
            </div>
            {item.notes && (
              <div className="mt-2 text-sm italic text-amber-500/80">
                "{item.notes}"
              </div>
            )}
          </div>
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="text-sm text-[var(--text-muted)]">
            Expected Refund
          </div>
          <div className="text-xl font-bold font-mono text-[var(--text-primary)]">
            {formatCurrency(item.expected_amount)}
          </div>
          {item.remaining !== undefined &&
            item.remaining > 0 &&
            item.remaining < item.expected_amount && (
              <div className="text-xs text-amber-500">
                Remaining: {formatCurrency(item.remaining)}
              </div>
            )}
        </div>
      </div>

      {/* Body: Linked Refunds */}
      <div className="p-4 border-t border-[var(--surface-light)]">
        <div className="text-sm font-medium text-[var(--text-muted)] mb-3 flex items-center gap-2">
          <Link size={14} />
          Linked Refunds
        </div>

        {!item.links || item.links.length === 0 ? (
          <div className="text-sm text-[var(--text-muted)] italic pl-6">
            No refunds linked yet.
          </div>
        ) : (
          <div className="space-y-2 pl-2 border-l-2 border-[var(--surface-light)] ml-1">
            {item.links.map((link) => (
              <div
                key={link.id}
                className="pl-4 py-1 flex justify-between items-center group"
              >
                <div className="flex items-center gap-2">
                  <span className="text-emerald-400 font-mono font-medium">
                    +{formatCurrency(link.amount)}
                  </span>
                  <span className="text-[var(--text-muted)]">•</span>
                  <span className="text-sm">
                    {link.description || "Refund Transaction"}
                  </span>
                  <span className="text-xs text-[var(--text-muted)]">
                    ({link.date})
                  </span>
                </div>
                <div className="text-xs text-[var(--text-muted)] uppercase opacity-50 group-hover:opacity-100 transition-opacity">
                  {link.refund_source}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="max-w-4xl mx-auto py-6 px-4">
      {groupedRefunds.active.length > 0 && (
        <section className="mb-8">
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-amber-400">
            <CircleDashed size={20} />
            Active ({groupedRefunds.active.length})
          </h2>
          {groupedRefunds.active.map(renderRefundCard)}
        </section>
      )}

      {groupedRefunds.resolved.length > 0 && (
        <section>
          <h2 className="text-lg font-semibold mb-4 flex items-center gap-2 text-emerald-400">
            <CheckCircle2 size={20} />
            Resolved ({groupedRefunds.resolved.length})
          </h2>
          {groupedRefunds.resolved.map(renderRefundCard)}
        </section>
      )}

      {(!refunds || refunds.length === 0) && (
        <div className="text-center py-12 text-[var(--text-muted)]">
          <ArrowLeftRight size={48} className="mx-auto mb-4 opacity-20" />
          <p>No refund expectations found.</p>
          <p className="text-sm mt-2">
            Mark expenses as "Pending Refund" in your transactions list to track
            them here.
          </p>
        </div>
      )}
    </div>
  );
};

export default RefundsView;
