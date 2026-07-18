import { useTranslation } from "react-i18next";
import {
  Trash2,
  Power,
  PowerOff,
  TrendingUp,
  BarChart2,
  DollarSign,
  Pencil,
  Settings,
} from "lucide-react";
import type { Investment } from "../../services/api";
import { Skeleton } from "../common/Skeleton";
import { Sparkline } from "../common/Sparkline";
import { InfoTooltip } from "../common/InfoTooltip";
import { useConfirm } from "../../context/DialogContext";
import {
  formatCurrency,
  formatChange,
  formatPercentChange,
} from "../../utils/numberFormatting";

export interface AllocationItem {
  id: number;
  name: string;
  balance: number;
  percentage: number;
  profit_loss?: number;
  roi?: number;
  history?: number[];
  total_deposits?: number;
  total_withdrawals?: number;
  cagr?: number;
}

const TYPE_KEY_MAP: Record<string, string> = {
  stocks: "stocks",
  crypto: "crypto",
  bonds: "bonds",
  real_estate: "realEstate",
  pension: "pension",
  brokerage_account: "brokerageAccount",
  p2p_lending: "p2pLending",
  other: "other",
};

export function InvestmentCard({
  inv,
  onViewAnalysis,
  onClose,
  onReopen,
  onDelete,
  onUpdateBalance,
  onEditCloseDate,
  onEdit,
  analysisData,
}: {
  inv: Investment;
  onViewAnalysis: (id: number) => void;
  onClose: (id: number) => void;
  onReopen: (id: number) => void;
  onDelete: (id: number) => void;
  onUpdateBalance: (id: number) => void;
  onEditCloseDate: (id: number, closedDate?: string) => void;
  onEdit: (inv: Investment) => void;
  analysisData?: AllocationItem;
}) {
  const { t } = useTranslation();
  const confirm = useConfirm();
  const snapshotAgeDays = inv.latest_snapshot_date
    ? Math.floor(
        (new Date().getTime() - new Date(inv.latest_snapshot_date).getTime()) /
          (1000 * 60 * 60 * 24)
      )
    : 0;

  return (
    <div
      className={`group bg-[var(--surface)] rounded-2xl border ${inv.is_closed ? "border-red-500/10" : "border-[var(--surface-light)]"} p-4 md:p-6 shadow-sm hover:shadow-xl transition-all flex flex-col`}
    >
      <div className="flex items-start justify-between mb-3 md:mb-4">
        <div className="flex items-center gap-2 md:gap-4">
          <div
            className={`p-3 rounded-xl ${inv.is_closed ? "bg-red-500/10 text-red-400" : "bg-emerald-500/10 text-emerald-400"}`}
          >
            <TrendingUp size={24} />
          </div>
          <div>
            <h3 className="font-bold text-lg text-white">{inv.name}</h3>
            <div className="flex items-center gap-2 mt-0.5">
              <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)]">
                {t(`investments.types.${TYPE_KEY_MAP[inv.type] || "other"}`)}
              </span>
              <span className="text-[var(--text-muted)]">•</span>
              <span className="text-xs text-[var(--text-muted)] font-medium">
                {inv.tag}
              </span>
            </div>
          </div>
        </div>
        {!!inv.is_closed && (
          <div className="px-2.5 py-1 rounded-lg text-[10px] font-black uppercase tracking-tighter bg-red-500/20 text-red-400">
            {t("investments.closed")}
          </div>
        )}
      </div>

      {/* Balance + Sparkline */}
      <div className="flex items-center justify-between mb-3 md:mb-4 p-3 md:p-4 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)]">
        <div>
          {analysisData ? (
            inv.is_closed ? (
              <>
                <p
                  className={`text-2xl font-black ${(analysisData.profit_loss ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                  dir="ltr"
                >
                  {formatChange(analysisData.profit_loss ?? 0, { compact: false })}
                </p>
                <p className="text-sm font-semibold mt-1 text-[var(--text-muted)]" dir="ltr">
                  {analysisData.roi != null &&
                    `ROI: ${formatPercentChange(analysisData.roi)}`}
                </p>
              </>
            ) : (
              <>
                <p className="text-2xl font-black text-white" dir="ltr">
                  {formatCurrency(analysisData.balance)}
                </p>
                <p
                  className={`text-sm font-semibold mt-1 ${(analysisData.profit_loss ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                  dir="ltr"
                >
                  {formatChange(analysisData.profit_loss ?? 0, { compact: false })}
                  {analysisData.roi != null &&
                    ` (${formatPercentChange(analysisData.roi)})`}
                </p>
              </>
            )
          ) : (
            <div className="space-y-2">
              <Skeleton variant="card" className="h-7 w-28" />
              <Skeleton variant="card" className="h-4 w-20" />
            </div>
          )}
        </div>
        <div className="flex-shrink-0 ms-4">
          {(analysisData?.history?.length ?? 0) >= 2 ? (
            <Sparkline
              data={analysisData!.history!}
              width={100}
              height={40}
              color={(analysisData!.profit_loss ?? 0) >= 0 ? "#10b981" : "#f43f5e"}
            />
          ) : !analysisData ? (
            <Skeleton variant="card" className="w-[100px] h-[40px]" />
          ) : null}
        </div>
      </div>

      {/* Metrics Strip */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 md:gap-3 mb-3 md:mb-4">
        <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">{t("investments.deposits")}</p>
          <p className="text-sm font-bold text-white mt-0.5">
            {analysisData ? formatCurrency(analysisData.total_deposits ?? 0) : "—"}
          </p>
        </div>
        <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">{t("investments.withdrawals")}</p>
          <p className="text-sm font-bold text-white mt-0.5">
            {analysisData ? formatCurrency(analysisData.total_withdrawals ?? 0) : "—"}
          </p>
        </div>
        <div className="text-center p-2 rounded-lg bg-[var(--surface-base)]">
          <p className="text-[9px] uppercase font-bold text-[var(--text-muted)] tracking-wider">{t("investments.cagr")}</p>
          <p className="text-sm font-bold text-white mt-0.5" dir="ltr">
            {analysisData?.cagr != null ? formatPercentChange(analysisData.cagr) : "—"}
          </p>
        </div>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[10px] text-[var(--text-muted)] font-medium mb-4 px-1">
        <span>{t("investments.opened")} {inv.first_transaction_date || inv.created_date}</span>
        {inv.latest_snapshot_date && (
          <>
            <span>·</span>
            <span className={snapshotAgeDays > 30 ? "text-amber-400" : ""}>
              {t("investments.updated")} {inv.latest_snapshot_date}
              {snapshotAgeDays > 30 ? ` (${t("investments.daysAgo", { count: snapshotAgeDays })})` : ""}
            </span>
          </>
        )}
        {!!inv.is_closed && inv.closed_date && (
          <>
            <span>·</span>
            <span className="text-red-400 inline-flex items-center gap-1">
              {t("investments.closed")} {inv.closed_date}
              <button
                onClick={() => onEditCloseDate(inv.id, inv.closed_date)}
                className="hover:text-white transition-all"
                title={t("tooltips.editCloseDate")}
              >
                <Pencil size={10} />
              </button>
            </span>
          </>
        )}
      </div>

      <div className="mt-auto flex items-center justify-between pt-4 border-t border-[var(--surface-light)]">
        <div className="flex gap-2">
          {!inv.is_closed ? (
            <button
              onClick={() => onClose(inv.id)}
              className="p-2 rounded-lg bg-red-500/10 text-red-400 hover:bg-red-500/20 transition-all"
              title={t("common.close")}
            >
              <PowerOff size={16} />
            </button>
          ) : (
            <button
              onClick={() => onReopen(inv.id)}
              className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 hover:bg-emerald-500/20 transition-all"
              title={t("investments.reopen")}
            >
              <Power size={16} />
            </button>
          )}
          <button
            onClick={async () => {
              const ok = await confirm({
                title: t("common.deleteTitle"),
                message: t("investments.confirmDelete"),
                confirmLabel: t("common.delete"),
                isDestructive: true,
              });
              if (ok) onDelete(inv.id);
            }}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-red-400 transition-all"
            title={t("common.delete")}
          >
            <Trash2 size={16} />
          </button>
          {inv.notes && (
            <div className="p-2 rounded-lg bg-[var(--surface-light)] flex items-center">
              <InfoTooltip text={inv.notes} iconSize={16} width={192} />
            </div>
          )}
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onEdit(inv)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title={t("common.edit")}
          >
            <Settings size={16} />
          </button>
          {!inv.is_closed && (
            <button
              onClick={() => onUpdateBalance(inv.id)}
              className="p-2 rounded-lg bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 transition-all"
              title={t("investments.updateBalance")}
            >
              <DollarSign size={16} />
            </button>
          )}
          <button
            onClick={() => onViewAnalysis(inv.id)}
            className="p-2 rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title={t("investments.viewAnalysis")}
          >
            <BarChart2 size={16} />
          </button>
        </div>
      </div>
    </div>
  );
}
