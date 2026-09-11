import { useState } from "react";
import { useNavigate } from "react-router";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  Heart,
  Percent,
  ChevronDown,
  ChevronUp,
  Landmark,
  Lock,
  Loader2,
  Pencil,
  Check,
  X,
  RotateCcw,
} from "lucide-react";
import {
  ResponsiveContainer,
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { AXIS_DEFAULTS, BAR_RADIUS, CHART_TEXT_COLOR, formatAxisNumber } from "../utils/chartStyle";
import { ChartTooltip } from "../components/charts/ChartTooltip";
import { ChartLegend } from "../components/charts/ChartLegend";
import { DonutChart } from "../components/charts/DonutChart";
import { insuranceAccountsApi, transactionsApi, type InsuranceAccount } from "../services/api";
import { formatDate, formatMonthCompact, formatMonthYear } from "../utils/dateFormatting";
import { formatCurrency } from "../utils/numberFormatting";
import { classifyStatement } from "../utils/insuranceStatement";
import { EmptyState } from "../components/common/EmptyState";
import { DemoModeConfirmPopover } from "../components/common/DemoModeConfirmPopover";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";

// ─── Types ───────────────────────────────────────────────────────────────
interface InsuranceTransaction {
  unique_id: number;
  date: string;
  description: string;
  amount: number;
  provider: string;
  account_number: string;
  account_name: string;
  memo: string | null;
}

interface Track {
  name: string;
  yield_pct: number;
  allocation_pct: number | null;
  sum: number | null;
}

interface Cover {
  title: string;
  desc: string;
  sum: number | { value: number; currency: string };
}

// ─── Helpers ─────────────────────────────────────────────────────────────
function fmtPct(val: number | null | undefined): string {
  if (val === null || val === undefined) return "—";
  return `${val.toFixed(2)}%`;
}

function fmtDate(d: string | null): string {
  if (!d) return "—";
  return formatDate(new Date(d));
}

/** Extract numeric value from a possibly-wrapped {value, currency} dict. */
function unwrapAmount(val: number | { value: number; currency: string } | null): number {
  if (val === null || val === undefined) return 0;
  if (typeof val === "object" && "value" in val) return val.value;
  return val;
}

function parseTracks(json: string | null): Track[] {
  if (!json) return [];
  try {
    return JSON.parse(json);
  } catch {
    return [];
  }
}

function parseCovers(json: string | null): Cover[] {
  if (!json) return [];
  try {
    return JSON.parse(json);
  } catch {
    return [];
  }
}

function parseMemo(memo: string | null): { employee: number | null; employer: number | null; compensation: number | null } {
  if (!memo) return { employee: null, employer: null, compensation: null };
  const result: { employee: number | null; employer: number | null; compensation: number | null } = {
    employee: null, employer: null, compensation: null,
  };
  for (const part of memo.split("/")) {
    const trimmed = part.trim();
    const match = trimmed.match(/^(.+?):\s*([\d.]+)$/);
    if (!match) continue;
    const [, label, val] = match;
    const num = parseFloat(val);
    if (label.includes("עובד")) result.employee = num;
    else if (label.includes("מעסיק")) result.employer = num;
    else if (label.includes("פיצויים")) result.compensation = num;
  }
  return result;
}

function policyTypeBadge(type: string, pensionType: string | null, t: (key: string) => string) {
  if (type === "pension") {
    const sub = pensionType === "makifa" ? t("insurance.makifa") : t("insurance.mashlima");
    return (
      <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-blue-500/15 text-blue-400">
        {t("insurance.pension")} · {sub}
      </span>
    );
  }
  return (
    <span className="px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider bg-purple-500/15 text-purple-400">
      {t("insurance.kerenHistahlmut")}
    </span>
  );
}

// ─── Shared Components ───────────────────────────────────────────────────
function StatCard({
  title,
  value,
  icon: Icon,
  color,
}: {
  title: string;
  value: string | number;
  icon: React.ComponentType<{ size: number }>;
  color: string;
}) {
  return (
    <div className="bg-[var(--surface)] rounded-xl p-5 border border-[var(--surface-light)] flex items-center justify-between">
      <div>
        <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold">{title}</p>
        <p className="text-xl font-black mt-1 text-white">{value}</p>
      </div>
      <div className={`p-3 rounded-xl ${color}`}>
        <Icon size={20} />
      </div>
    </div>
  );
}

function CoversSection({ id, covers }: { id: string; covers: Cover[] }) {
  const { t } = useTranslation();
  return (
    <div id={id} className="px-4 sm:px-6 pb-4">
      <p className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest font-bold mb-2">
        {t("insurance.monthlyAmounts")}
      </p>
      <div className="flex flex-col gap-2">
        {covers.map((cover, i) => (
          <div
            key={i}
            data-testid="insurance-cover-row"
            className="flex items-start justify-between gap-4 border-b border-[var(--surface-light)]/30 pb-2 last:border-0"
          >
            <div className="min-w-0">
              <p className="text-white text-sm font-semibold" dir="auto">
                {cover.title}
              </p>
              {cover.desc && (
                <p className="text-[var(--text-muted)] text-xs mt-0.5" dir="auto">
                  {cover.desc}
                </p>
              )}
            </div>
            <span
              className="text-white font-mono font-bold text-sm whitespace-nowrap shrink-0"
              dir="ltr"
            >
              {formatCurrency(unwrapAmount(cover.sum))}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Account Card ────────────────────────────────────────────────────────
function AccountCardFull({
  account,
  transactions,
}: {
  account: InsuranceAccount;
  transactions: InsuranceTransaction[];
}) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  // One slot, so opening covers closes deposits (and vice versa) — the card
  // can never grow by both sections at once.
  const [expandedSection, setExpandedSection] = useState<"covers" | "deposits" | null>(null);
  const toggleSection = (section: "covers" | "deposits") =>
    setExpandedSection((current) => (current === section ? null : section));
  const coversSectionId = `covers-${account.policy_id}`;
  const depositsSectionId = `deposits-${account.policy_id}`;
  const [isEditingName, setIsEditingName] = useState(false);
  const [draftName, setDraftName] = useState("");
  const tracks = parseTracks(account.investment_tracks);
  const covers = parseCovers(account.insurance_covers);
  const statement = classifyStatement(account.insurance_costs);
  const txs = transactions
    .filter((tx) => tx.account_number === account.policy_id)
    .sort((a, b) => b.date.localeCompare(a.date));
  const deposits = txs.filter((tx) => tx.amount > 0);

  const renameMutation = useMutation({
    mutationFn: (customName: string | null) =>
      insuranceAccountsApi.rename(account.policy_id, customName),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.insuranceAccounts });
      queryClient.invalidateQueries({ queryKey: qkPrefix.investments });
      setIsEditingName(false);
      setDraftName("");
    },
  });

  const displayName = account.custom_name || account.account_name;
  const stripeColor = account.policy_type === "pension" ? "bg-blue-400" : "bg-purple-400";

  const startEditing = () => {
    setDraftName(account.custom_name ?? "");
    setIsEditingName(true);
  };

  const cancelEditing = () => {
    setIsEditingName(false);
    setDraftName("");
  };

  const saveName = () => {
    const trimmed = draftName.trim();
    renameMutation.mutate(trimmed || null);
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden relative">
      {/* Policy-type accent stripe */}
      <div className={`absolute inset-y-0 start-0 w-1 ${stripeColor}`} />

      {/* Header */}
      <div className="ps-5 pe-4 sm:ps-7 sm:pe-6 py-5 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div className="min-w-0 flex-1">
          {isEditingName ? (
            <div className="flex flex-col gap-2">
              <div className="flex items-center gap-2 flex-wrap">
                <input
                  type="text"
                  value={draftName}
                  onChange={(e) => setDraftName(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") saveName();
                    if (e.key === "Escape") cancelEditing();
                  }}
                  placeholder={account.account_name}
                  disabled={renameMutation.isPending}
                  autoFocus
                  aria-label={t("insurance.renameFund")}
                  className="flex-1 min-w-[160px] bg-[var(--surface-light)] text-white rounded-lg px-3 py-1.5 text-base sm:text-lg font-bold border border-[var(--surface-light)] focus:border-[var(--accent)] outline-none"
                />
                <button
                  type="button"
                  onClick={saveName}
                  disabled={renameMutation.isPending}
                  aria-label={t("insurance.save")}
                  title={t("insurance.save")}
                  className="w-[36px] h-[36px] flex items-center justify-center rounded-lg bg-emerald-500/20 text-emerald-300 hover:bg-emerald-500/30 disabled:opacity-50"
                >
                  <Check size={16} />
                </button>
                <button
                  type="button"
                  onClick={cancelEditing}
                  disabled={renameMutation.isPending}
                  aria-label={t("insurance.cancel")}
                  title={t("insurance.cancel")}
                  className="w-[36px] h-[36px] flex items-center justify-center rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"
                >
                  <X size={16} />
                </button>
                {account.custom_name && (
                  <button
                    type="button"
                    onClick={() => renameMutation.mutate(null)}
                    disabled={renameMutation.isPending}
                    aria-label={t("insurance.resetToScrapedName")}
                    title={t("insurance.resetToScrapedName")}
                    className="w-[36px] h-[36px] flex items-center justify-center rounded-lg bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white"
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
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-white font-bold text-base sm:text-lg break-words">
                  {displayName}
                </h3>
                {policyTypeBadge(account.policy_type, account.pension_type, t)}
                <button
                  type="button"
                  onClick={startEditing}
                  aria-label={t("insurance.renameFund")}
                  title={t("insurance.renameFund")}
                  className="shrink-0 w-[32px] h-[32px] flex items-center justify-center rounded-lg text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] transition-colors"
                >
                  <Pencil size={14} />
                </button>
              </div>
              {account.custom_name && (
                <p className="text-[10px] text-[var(--text-muted)] mt-0.5 italic truncate" dir="auto">
                  {account.account_name}
                </p>
              )}
            </>
          )}
          <p className="text-xs text-[var(--text-muted)] mt-0.5 truncate">
            {t("insurance.policy")} {account.policy_id} · {t("insurance.updated")} {fmtDate(account.balance_date)}
          </p>
        </div>
        <div className="text-start sm:text-end shrink-0">
          <p className="text-2xl font-black text-white">{formatCurrency(account.balance ?? 0)}</p>
          <p className="text-xs text-[var(--text-muted)]">{t("insurance.currentBalance")}</p>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="px-4 sm:px-6 pb-4 grid grid-cols-2 sm:grid-cols-4 gap-3">
        {/* Investment Tracks */}
        <div className="bg-[var(--background)]/50 rounded-xl p-3">
          <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">
            {t("insurance.investmentTracks")}
          </p>
          {tracks.map((track, i) => (
            <div key={i} className="flex justify-between items-center text-xs mb-1">
              <span className="text-[var(--text-muted)] truncate me-2" dir="auto">{track.name}</span>
              <span
                className={`font-mono font-bold whitespace-nowrap ${track.yield_pct >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                dir="ltr"
              >
                {track.yield_pct > 0 ? "+" : ""}
                {track.yield_pct}%
              </span>
            </div>
          ))}
          {tracks.length > 1 && (
            <div className="mt-2 flex gap-1">
              {tracks.map((track, i) => (
                <div
                  key={i}
                  className="h-1.5 rounded-full bg-blue-500"
                  style={{
                    width: `${track.allocation_pct ?? 50}%`,
                    opacity: 0.4 + i * 0.3,
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Commissions */}
        <div className="bg-[var(--background)]/50 rounded-xl p-3">
          <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">{t("insurance.commissions")}</p>
          <div className="flex justify-between text-xs mb-1">
            <span className="text-[var(--text-muted)]">{t("insurance.fromDeposits")}</span>
            <span className="text-amber-400 font-mono font-bold" dir="ltr">
              {fmtPct(account.commission_deposits_pct)}
            </span>
          </div>
          <div className="flex justify-between text-xs">
            <span className="text-[var(--text-muted)]">{t("insurance.fromSavings")}</span>
            <span className="text-amber-400 font-mono font-bold" dir="ltr">
              {fmtPct(account.commission_savings_pct)}
            </span>
          </div>
        </div>

        {/* Deposit Summary */}
        <div className="bg-[var(--background)]/50 rounded-xl p-3">
          <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">{t("insurance.deposits")}</p>
          <p className="text-emerald-400 font-black text-lg" dir="ltr">{formatCurrency(deposits.reduce((s, dep) => s + dep.amount, 0))}</p>
          <p className="text-[var(--text-muted)] text-[10px]">{t("insurance.totalDepositsCount", { count: deposits.length })}</p>
          {statement.riskCost > 0 && (
            <p
              data-testid="insurance-risk-cost"
              className="text-rose-400 text-[10px] mt-1 font-bold"
            >
              {t("insurance.riskCost")}{" "}
              <span dir="ltr">{formatCurrency(-statement.riskCost)}</span> ·{" "}
              {t("insurance.thisYear")}
            </p>
          )}
          {statement.managementFee > 0 && (
            <p
              data-testid="insurance-mgmt-fee"
              className="text-[var(--text-muted)] text-[10px] font-bold"
            >
              {t("insurance.managementFeeAmount")}{" "}
              <span dir="ltr">{formatCurrency(-statement.managementFee)}</span> ·{" "}
              {t("insurance.thisYear")}
            </p>
          )}
          {/* Deductions we saw but could not name. Rendered beside the two
              classified lines because that is exactly where a renamed
              provider row goes missing: the red risk-cost line vanishes and
              a ₪0 takes its place, which reads as "no risk cost" rather
              than "we stopped recognising the row". */}
          {statement.unclassified > 0 && (
            <p
              data-testid="insurance-unclassified"
              title={t("insurance.unclassifiedDeductionsHint")}
              className="text-amber-400 text-[10px] font-bold"
            >
              {t("insurance.unclassifiedDeductions")}{" "}
              <span dir="ltr">{formatCurrency(-statement.unclassified)}</span> ·{" "}
              {t("insurance.thisYear")}
            </p>
          )}
        </div>

        {/* Insurance Covers / Liquidity / Activity (last column — variable content) */}
        {covers.length > 0 ? (
          <div
            data-testid="insurance-covers-summary"
            className="bg-[var(--background)]/50 rounded-xl p-3"
          >
            <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">
              {t("insurance.insuranceCovers")}
            </p>
            {/* Headline is covers[0] by scrape order — the provider lists the
                retirement annuity first. Ordinal beats title matching (no
                hardcoded Hebrew) and beats largest-value (that surfaces a
                death benefit, not the headline figure). */}
            <p className="text-white font-black text-lg" dir="ltr">
              {formatCurrency(unwrapAmount(covers[0].sum))}
              <span className="text-[10px] font-bold text-[var(--text-muted)] ms-1">
                {t("insurance.perMonth")}
              </span>
            </p>
            <p
              className="text-[var(--text-muted)] text-[10px] truncate"
              dir="auto"
              title={covers[0].title}
            >
              {covers[0].title}
            </p>
            <button
              type="button"
              data-testid="insurance-covers-count"
              aria-expanded={expandedSection === "covers"}
              aria-controls={coversSectionId}
              onClick={() => toggleSection("covers")}
              className="mt-1 text-[10px] font-bold text-blue-400 hover:text-blue-300"
            >
              {t("insurance.coversCount", { count: covers.length })}
            </button>
          </div>
        ) : account.liquidity_date ? (
          <div className="bg-[var(--background)]/50 rounded-xl p-3">
            <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">
              {t("insurance.liquidityDate")}
            </p>
            <div className="flex items-center gap-2">
              <Lock size={14} className="text-purple-400" />
              <span className="text-white font-bold text-sm">{fmtDate(account.liquidity_date)}</span>
            </div>
            <p className="text-[var(--text-muted)] text-[10px] mt-1">
              {new Date(account.liquidity_date) > new Date() ? t("insurance.locked") : t("insurance.available")}
            </p>
          </div>
        ) : (
          <div className="bg-[var(--background)]/50 rounded-xl p-3">
            <p className="text-[var(--text-muted)] text-[9px] uppercase tracking-widest font-bold mb-2">{t("insurance.activity")}</p>
            <p className="text-white font-bold text-lg">{deposits.length}</p>
            <p className="text-[var(--text-muted)] text-[10px]">{t("insurance.deposits")}</p>
          </div>
        )}
      </div>

      {/* Expandable footer: covers list and deposit history share one slot */}
      <div className="border-t border-[var(--surface-light)]">
        <div className="flex flex-col sm:flex-row">
          {covers.length > 0 && (
            <button
              type="button"
              data-testid="insurance-covers-toggle"
              aria-expanded={expandedSection === "covers"}
              aria-controls={coversSectionId}
              onClick={() => toggleSection("covers")}
              className="flex-1 px-6 py-3 flex items-center justify-between text-sm text-[var(--text-muted)] hover:text-white transition-colors"
            >
              <span>
                {expandedSection === "covers"
                  ? t("insurance.hideInsuranceCovers")
                  : t("insurance.showInsuranceCovers")}{" "}
                ({covers.length})
              </span>
              {expandedSection === "covers" ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
            </button>
          )}
          <button
            type="button"
            data-testid="insurance-deposits-toggle"
            aria-expanded={expandedSection === "deposits"}
            aria-controls={depositsSectionId}
            onClick={() => toggleSection("deposits")}
            className="flex-1 px-6 py-3 flex items-center justify-between text-sm text-[var(--text-muted)] hover:text-white transition-colors"
          >
            <span>
              {expandedSection === "deposits"
                ? t("insurance.hideDepositHistory")
                : t("insurance.showDepositHistory")}{" "}
              ({txs.length} {t("insurance.transactions")})
            </span>
            {expandedSection === "deposits" ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
        </div>
        {expandedSection === "covers" && <CoversSection id={coversSectionId} covers={covers} />}
        {expandedSection === "deposits" && (
          <div id={depositsSectionId} className="overflow-x-auto max-h-80 overflow-y-auto">
            <table className="w-full text-sm">
              <thead className="sticky top-0 bg-[var(--surface)]">
                <tr className="text-[var(--text-muted)] text-[10px] uppercase tracking-widest border-b border-[var(--surface-light)]">
                  <th className="text-start px-4 sm:px-6 py-2 font-bold">{t("common.date")}</th>
                  <th className="text-start px-4 sm:px-6 py-2 font-bold">{t("common.description")}</th>
                  {account.policy_type === "pension" && (
                    <>
                      <th className="text-end px-4 sm:px-6 py-2 font-bold">{t("insurance.employee")}</th>
                      <th className="text-end px-4 sm:px-6 py-2 font-bold">{t("insurance.employer")}</th>
                      <th className="text-end px-4 sm:px-6 py-2 font-bold">{t("insurance.compensation")}</th>
                    </>
                  )}
                  <th className="text-end px-4 sm:px-6 py-2 font-bold">{t("common.total")}</th>
                </tr>
              </thead>
              <tbody>
                {txs.map((tx) => {
                  const breakdown = account.policy_type === "pension" ? parseMemo(tx.memo) : null;
                  return (
                    <tr
                      key={tx.unique_id}
                      className="border-b border-[var(--surface-light)]/30 hover:bg-[var(--surface-light)]/20 transition-colors"
                    >
                      <td className="px-4 sm:px-6 py-2 text-[var(--text-muted)] whitespace-nowrap">{tx.date}</td>
                      <td className="px-4 sm:px-6 py-2 text-white">{tx.description}</td>
                      {breakdown !== null && (
                        <>
                          <td className="px-4 sm:px-6 py-2 text-end font-mono text-xs text-[var(--text-muted)]">
                            {breakdown.employee !== null ? formatCurrency(breakdown.employee) : "—"}
                          </td>
                          <td className="px-4 sm:px-6 py-2 text-end font-mono text-xs text-[var(--text-muted)]">
                            {breakdown.employer !== null ? formatCurrency(breakdown.employer) : "—"}
                          </td>
                          <td className="px-4 sm:px-6 py-2 text-end font-mono text-xs text-[var(--text-muted)]">
                            {breakdown.compensation !== null ? formatCurrency(breakdown.compensation) : "—"}
                          </td>
                        </>
                      )}
                      <td className="px-4 sm:px-6 py-2 text-end whitespace-nowrap">
                        <span
                          className={`font-mono font-bold ${tx.amount >= 0 ? "text-emerald-400" : "text-rose-400"}`}
                          dir="ltr"
                        >
                          {tx.amount >= 0 ? "+" : ""}
                          {formatCurrency(tx.amount)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ───────────────────────────────────────────────────────────
export function Insurances() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [showDemoConfirm, setShowDemoConfirm] = useState(false);
  const qk = useQueryKeys();
  const { data: accountsData, isLoading: accountsLoading } = useQuery({
    queryKey: qk.insurance.accounts(),
    queryFn: () => insuranceAccountsApi.getAll().then((r) => r.data),
  });

  const { data: transactionsData, isLoading: txLoading } = useQuery({
    queryKey: qk.transactions.list("insurances", false),
    queryFn: () =>
      transactionsApi.getAll("insurances").then((r) => r.data as InsuranceTransaction[]),
  });

  const accounts = accountsData ?? [];
  const transactions = transactionsData ?? [];
  const isLoading = accountsLoading || txLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-96 text-[var(--text-muted)]">
        <Loader2 size={24} className="animate-spin me-2" />
        {t("insurance.loadingData")}
      </div>
    );
  }

  if (accounts.length === 0) {
    return (
      <EmptyState
        title={t("emptyStates.insurance.title")}
        description={t("emptyStates.insurance.description")}
        cta={{
          label: t("emptyStates.connectAccounts"),
          onClick: () => navigate("/data-sources"),
        }}
        secondary={{
          label: t("emptyStates.tryDemoMode"),
          onClick: () => setShowDemoConfirm(true),
        }}
        footer={
          showDemoConfirm ? (
            <DemoModeConfirmPopover onClose={() => setShowDemoConfirm(false)} />
          ) : undefined
        }
      />
    );
  }

  const totalBalance = accounts.reduce((s, a) => s + (a.balance ?? 0), 0);
  const allDeposits = transactions.filter((tx) => tx.amount > 0);
  const totalDeposits = allDeposits.reduce((s, tx) => s + tx.amount, 0);
  // Risk cost only — the management fee is shown per-card beside its own rate.
  const totalRiskCost = accounts.reduce(
    (s, a) => s + classifyStatement(a.insurance_costs).riskCost,
    0,
  );
  const avgCommission =
    accounts.reduce((s, a) => s + (a.commission_savings_pct ?? 0), 0) / accounts.length;

  // Monthly deposit aggregation for chart
  const monthlyDeposits: Record<string, number> = {};
  allDeposits.forEach((tx) => {
    const month = tx.date.substring(0, 7);
    monthlyDeposits[month] = (monthlyDeposits[month] || 0) + tx.amount;
  });
  const months = Object.keys(monthlyDeposits).sort();
  const monthlyValues = months.map((m) => monthlyDeposits[m]);
  const cumulativeValues = monthlyValues.reduce((acc: number[], v) => {
    acc.push((acc.length > 0 ? acc[acc.length - 1] : 0) + v);
    return acc;
  }, []);

  // Allocation across all accounts
  const allTracks = accounts.flatMap((a) => {
    const tracks = parseTracks(a.investment_tracks);
    return tracks.map((track) => ({ ...track, account: a.account_name }));
  });
  // Filter to tracks with a non-zero sum for the pie chart
  const tracksWithSum = allTracks.filter((track) => (track.sum ?? 0) > 0);
  const trackNames = tracksWithSum.map((track) => track.name);
  const trackSums = tracksWithSum.map((track) => track.sum ?? 0);

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-4">
        <StatCard title={t("insurance.totalBalance")} value={formatCurrency(totalBalance)} icon={Landmark} color="bg-blue-500/10 text-blue-400" />
        <StatCard
          title={t("insurance.totalDeposits")}
          value={formatCurrency(totalDeposits)}
          icon={ArrowUpRight}
          color="bg-emerald-500/10 text-emerald-400"
        />
        <StatCard
          title={t("insurance.riskCostsThisYear")}
          value={formatCurrency(totalRiskCost)}
          icon={Heart}
          color="bg-rose-500/10 text-rose-400"
        />
        <StatCard
          title={t("insurance.avgCommission")}
          value={fmtPct(avgCommission)}
          icon={Percent}
          color="bg-amber-500/10 text-amber-400"
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Monthly deposits chart */}
        <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-5">
          <h3 className="text-white font-bold mb-1">{t("insurance.depositTrends")}</h3>
          <p className="text-[var(--text-muted)] text-xs mb-4">{t("insurance.depositTrendsDesc")}</p>
          <div style={{ height: 280 }}>
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart
                data={months.map((m, i) => ({
                  month: m,
                  monthly: monthlyValues[i],
                  cumulative: cumulativeValues[i],
                }))}
                margin={{ top: 8, bottom: 4, left: 0, right: 0 }}
              >
                <XAxis
                  dataKey="month"
                  {...AXIS_DEFAULTS}
                  tick={{ fill: "#64748b", fontSize: 10 }}
                  tickFormatter={formatMonthCompact}
                />
                <YAxis
                  yAxisId="left"
                  {...AXIS_DEFAULTS}
                  tick={{ fill: "#64748b", fontSize: 10 }}
                  tickFormatter={formatAxisNumber}
                  width={48}
                  label={{
                    value: t("insurance.chartMonthly"),
                    angle: -90,
                    position: "insideLeft",
                    style: { fill: CHART_TEXT_COLOR, fontSize: 10 },
                  }}
                />
                <YAxis
                  yAxisId="right"
                  orientation="right"
                  {...AXIS_DEFAULTS}
                  tick={{ fill: "#64748b", fontSize: 10 }}
                  tickFormatter={formatAxisNumber}
                  width={48}
                  label={{
                    value: t("insurance.chartCumulative"),
                    angle: 90,
                    position: "insideRight",
                    style: { fill: CHART_TEXT_COLOR, fontSize: 10 },
                  }}
                />
                <Tooltip
                  cursor={false}
                  content={<ChartTooltip labelFormatter={(m) => formatMonthYear(String(m) + "-01")} />}
                />
                <Legend
                  verticalAlign="top"
                  content={<ChartLegend fontSize={10} gapTop={0} />}
                  wrapperStyle={{ paddingBottom: 6 }}
                />
                <Bar
                  yAxisId="left"
                  dataKey="monthly"
                  name={t("insurance.chartMonthly")}
                  fill="#10b981"
                  fillOpacity={0.85}
                  radius={BAR_RADIUS}
                  isAnimationActive={false}
                />
                <Line
                  yAxisId="right"
                  dataKey="cumulative"
                  name={t("insurance.chartCumulative")}
                  type="monotone"
                  stroke="#3b82f6"
                  strokeWidth={2.5}
                  dot={false}
                  isAnimationActive={false}
                />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Allocation pie */}
        <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-5">
          <h3 className="text-white font-bold mb-1">{t("insurance.investmentAllocation")}</h3>
          <p className="text-[var(--text-muted)] text-xs mb-4">{t("insurance.investmentAllocationDesc")}</p>
          {tracksWithSum.length > 0 ? (
            <DonutChart
              data={trackNames.map((name, i) => ({ name, value: trackSums[i] }))}
              sorted
              height={280}
              labelMode="label-percent-outside"
              centerLabel={
                <span className="text-base font-semibold text-[#f8fafc]">{formatCurrency(totalBalance)}</span>
              }
            />
          ) : (
            <div className="flex items-center justify-center h-[280px] text-[var(--text-muted)] text-sm">
              {t("insurance.noTrackData")}
            </div>
          )}
        </div>
      </div>

      {/* Per-account rich cards */}
      {accounts.map((account) => (
        <AccountCardFull key={account.id} account={account} transactions={transactions} />
      ))}
    </div>
  );
}
