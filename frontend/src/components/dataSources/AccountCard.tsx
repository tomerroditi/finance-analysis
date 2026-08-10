import { useTranslation } from "react-i18next";
import {
  Trash2,
  Edit2,
  Eye,
  DollarSign,
  RefreshCw,
  PlayCircle,
  Smartphone,
  XCircle,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";
import type { BankBalance, CredentialAccount } from "../../services/api";
import type { ResendError, ScraperState } from "../../hooks/useScraping";
import { ProviderLogo } from "../common/ProviderLogo";
import { ScrapeErrorTooltip } from "../common/ScrapeErrorTooltip";
import { humanizeAccountType, humanizeProvider } from "../../utils/textFormatting";
import { formatRelativeDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";
import { needsAttention } from "./sourceHealth";

interface AccountCardProps {
  acc: CredentialAccount;
  scraper: ScraperState | undefined;
  lastScrapeDate: string | null | undefined;
  balance: BankBalance | undefined;
  /** Whether this account was scraped today (gates balance entry + badge). */
  scrapedToday: boolean;
  /**
   * True while this account's own `/scraping/start` request is in flight.
   * Scraping is per-account and parallel, so only this account's buttons wait
   * — a scrape running elsewhere never blocks starting this one.
   */
  isStartPending: boolean;
  /**
   * True while THIS account's 2FA code is being verified. Must stay
   * per-account: two accounts can sit on a 2FA prompt simultaneously, and a
   * shared flag would grey out one card's Verify/Resend while the other's
   * code is in flight.
   */
  tfaIsPending: boolean;
  tfaCode: string;
  onTfaCodeChange: (code: string) => void;
  onSubmitTfa: (code: string) => void;
  onResendTfa: () => void;
  resendCooldownRemaining: number;
  resendErrorInfo: ResendError | undefined;
  onStartScrape: (opts?: { force2fa?: boolean }) => void;
  onAbortScrape: () => void;
  onOpenBalanceModal: () => void;
  onView: () => void;
  onEdit: () => void;
  /** Requests disconnection — the page opens the keep-or-delete-data modal. */
  onDelete: () => void;
}

/**
 * Per-service accent, reused from the connect-account service chooser so a
 * card reads as the same "kind of thing" the user picked when adding it. The
 * left stripe is the same device the Insurances page uses to type its cards.
 */
const SERVICE_ACCENT: Record<string, string> = {
  banks: "bg-blue-400",
  credit_cards: "bg-purple-400",
  insurances: "bg-emerald-400",
};

/** Shared shell for the small label-over-value tiles inside a card. */
function StatTile({
  label,
  children,
  action,
}: {
  label: string;
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl bg-[var(--surface-base)] p-3 flex items-start justify-between gap-2 min-w-0">
      <div className="min-w-0">
        <p className="text-[9px] uppercase font-bold tracking-wider text-[var(--text-muted)]">
          {label}
        </p>
        <div className="mt-1">{children}</div>
      </div>
      {action}
    </div>
  );
}

/**
 * One connected-account card on the Data Sources page.
 *
 * Layout follows the page-card pattern the rest of the app uses (Liabilities,
 * Insurances): service-coloured accent stripe, identity block with an icon
 * tile, a status pill on the opposite side, a row of label-over-value stat
 * tiles, then actions on their own divided footer row. The inline 2FA prompt
 * stays attached to the bottom of the card so the code input appears next to
 * the account it belongs to.
 */
export function AccountCard({
  acc,
  scraper,
  lastScrapeDate,
  balance,
  scrapedToday,
  isStartPending,
  tfaIsPending,
  tfaCode,
  onTfaCodeChange,
  onSubmitTfa,
  onResendTfa,
  resendCooldownRemaining,
  resendErrorInfo,
  onStartScrape,
  onAbortScrape,
  onOpenBalanceModal,
  onView,
  onEdit,
  onDelete,
}: AccountCardProps) {
  const { t } = useTranslation();
  const isActive =
    scraper && (scraper.status === "in_progress" || scraper.status === "waiting_for_2fa");
  const isWaitingForCode = scraper?.status === "waiting_for_2fa";

  const submitCode = () => {
    if (tfaCode) onSubmitTfa(tfaCode);
  };

  /**
   * The one-line "what is this source doing" pill. A live scrape wins over
   * history; when nothing is running it only speaks up if there's something to
   * say (synced today, or overdue) rather than restating the Last-sync tile.
   */
  const statusPill = () => {
    if (scraper?.status === "in_progress") {
      return (
        <span className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-blue-500/15 border border-blue-500/30">
          <RefreshCw size={12} className="animate-spin text-blue-400" />
          <span className="text-[10px] font-black uppercase tracking-tighter text-blue-400">
            {t("dataSources.scraping")}
          </span>
        </span>
      );
    }
    if (scraper?.status === "waiting_for_2fa") {
      return (
        <span className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/15 border border-amber-500/30">
          <Smartphone size={12} className="text-amber-400 animate-pulse" />
          <span className="text-[10px] font-black uppercase tracking-tighter text-amber-400">
            {t("dataSources.tfaRequired")}
          </span>
        </span>
      );
    }
    if (scraper?.status === "failed") {
      return (
        <span className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-rose-500/15 border border-rose-500/30">
          <span className="text-[10px] font-black uppercase tracking-tighter text-rose-400">
            {t("dataSources.failed")}
          </span>
          {/* Rendered whenever either half is present: a category with no
              detail still yields a useful explanation, and a legacy row with
              only a message still shows that message. */}
          {(!!scraper.error_message || !!scraper.error_type) && (
            <ScrapeErrorTooltip
              message={scraper.error_message}
              errorType={scraper.error_type}
            />
          )}
        </span>
      );
    }
    if (scraper?.status === "success" || scrapedToday) {
      return (
        <span className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30">
          <CheckCircle2 size={12} className="text-emerald-400" />
          <span className="text-[10px] font-black uppercase tracking-tighter text-emerald-400">
            {t("dataSources.synced")}
          </span>
        </span>
      );
    }
    if (needsAttention(lastScrapeDate ?? null)) {
      return (
        <span className="shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/25">
          <AlertTriangle size={12} className="text-amber-400" />
          <span className="text-[10px] font-black uppercase tracking-tighter text-amber-400">
            {t("dataSources.needsSync")}
          </span>
        </span>
      );
    }
    return null;
  };

  return (
    <div className="group relative bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden shadow-sm hover:border-[var(--primary)]/30 hover:shadow-xl transition-all">
      {/* Service accent stripe */}
      <div
        className={`absolute inset-y-0 inset-inline-start-0 w-1 ${
          SERVICE_ACCENT[acc.service] ?? "bg-[var(--surface-light)]"
        }`}
      />

      <div className="ps-4 pe-3 md:ps-6 md:pe-5 py-4 md:py-5">
        {/* Identity + status */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-3 min-w-0">
            <div className="w-12 h-12 shrink-0 rounded-xl bg-white flex items-center justify-center p-1.5 text-gray-700">
              <ProviderLogo
                provider={acc.provider}
                service={acc.service}
                size={32}
                alt={humanizeProvider(acc.provider)}
              />
            </div>
            <div className="min-w-0">
              <h3
                className="font-bold text-base md:text-lg text-white truncate"
                dir="auto"
              >
                {acc.account_name}
              </h3>
              <p className="text-xs text-[var(--text-muted)] font-medium flex flex-wrap items-center gap-x-1.5">
                <span>{humanizeProvider(acc.provider)}</span>
                <span aria-hidden="true">·</span>
                <span>{humanizeAccountType(acc.service)}</span>
              </p>
            </div>
          </div>
          {statusPill()}
        </div>

        {/* Stat tiles */}
        <div
          className={`mt-4 grid gap-2 md:gap-3 ${
            acc.service === "banks" ? "grid-cols-2" : "grid-cols-1"
          }`}
        >
          <StatTile label={t("dataSources.lastSync")}>
            {lastScrapeDate ? (
              <p className="text-sm font-bold text-white truncate">
                {formatRelativeDate(lastScrapeDate)}
              </p>
            ) : (
              <p className="text-sm font-bold text-[var(--text-muted)] italic">
                {t("dataSources.neverSynced")}
              </p>
            )}
          </StatTile>

          {acc.service === "banks" && (
            <StatTile
              label={t("dataSources.balanceLabel")}
              action={
                <button
                  onClick={onOpenBalanceModal}
                  disabled={!scrapedToday}
                  className={`shrink-0 w-[32px] h-[32px] flex items-center justify-center rounded-lg transition-all ${
                    scrapedToday
                      ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                      : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
                  }`}
                  title={
                    scrapedToday
                      ? t("dataSources.setBalance")
                      : t("dataSources.scrapeFirstToSetBalance")
                  }
                >
                  <DollarSign size={16} />
                </button>
              }
            >
              {balance ? (
                <p className="text-sm font-bold text-amber-400 truncate">
                  {formatCurrency(balance.balance)}
                </p>
              ) : (
                <p className="text-xs font-bold text-[var(--text-muted)] italic">
                  {t("dataSources.noBalanceSet")}
                </p>
              )}
            </StatTile>
          )}
        </div>

        {/* Actions */}
        <div className="mt-4 pt-3 border-t border-[var(--surface-light)] flex items-center gap-2">
          {isActive ? (
            <button
              onClick={onAbortScrape}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-red-500/10 text-red-400 text-xs font-bold hover:bg-red-500/20 hover:text-red-300 transition-all"
              title={t("dataSources.abortScraping")}
            >
              <XCircle size={16} />
              {t("dataSources.stopScrape")}
            </button>
          ) : (
            <button
              // Deliberately NOT disabled while other accounts scrape: sources
              // are independent and run in parallel, so the user can click one
              // after another. Only this account's in-flight start is guarded.
              onClick={() => onStartScrape()}
              disabled={isStartPending}
              className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-[var(--primary)]/10 text-[var(--primary)] text-xs font-bold hover:bg-[var(--primary)]/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              title={t("dataSources.scrapeThisSource")}
            >
              {isStartPending ? (
                <RefreshCw size={16} className="animate-spin" />
              ) : (
                <PlayCircle size={16} />
              )}
              {t("dataSources.scrapeNow")}
            </button>
          )}
          {acc.provider === "onezero" && (
            <button
              onClick={() => onStartScrape({ force2fa: true })}
              disabled={isStartPending || isActive}
              className="w-[36px] h-[36px] flex items-center justify-center rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-amber-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              title={t("dataSources.forceTfaTitle")}
              aria-label={t("dataSources.forceTfa")}
            >
              <span className="relative inline-flex">
                <Smartphone size={18} />
                <RefreshCw
                  size={10}
                  className="absolute -bottom-1 -end-1.5 rounded-full bg-[var(--surface-light)] p-[1px] text-amber-400"
                />
              </span>
            </button>
          )}

          <div className="ms-auto flex items-center gap-1">
            <button
              onClick={onView}
              className="w-[36px] h-[36px] flex items-center justify-center rounded-xl text-[var(--text-muted)] hover:text-white hover:bg-[var(--surface-light)] transition-all"
              title={t("dataSources.viewDetails")}
            >
              <Eye size={18} />
            </button>
            <button
              onClick={onEdit}
              className="w-[36px] h-[36px] flex items-center justify-center rounded-xl text-[var(--text-muted)] hover:text-[var(--primary)] hover:bg-[var(--surface-light)] transition-all"
              title={t("dataSources.editAccount")}
            >
              <Edit2 size={18} />
            </button>
            <button
              // Confirmation lives in the page's DisconnectAccountModal — the
              // user must pick keep-data vs delete-data there, which a boolean
              // confirm() dialog can't express.
              onClick={onDelete}
              className="w-[36px] h-[36px] flex items-center justify-center rounded-xl text-[var(--text-muted)] hover:text-white hover:bg-red-500 transition-all"
              title={t("dataSources.disconnectAccount")}
            >
              <Trash2 size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* 2FA prompt — attached to the bottom of the card it belongs to. */}
      {isWaitingForCode && (() => {
        // Rate-limit detail is the backend's own actionable
        // wait-and-retry hint — show it verbatim. Everything else
        // gets a translated message (backend strings are
        // English-only and not meant for direct display).
        const resendError = resendErrorInfo
          ? resendErrorInfo.kind === "rate_limited" && resendErrorInfo.detail
            ? resendErrorInfo.detail
            : resendErrorInfo.kind === "expired"
              ? t("dataSources.resendProcessExpired")
              : t("dataSources.resendFailed")
          : undefined;
        return (
          <div className="ps-4 pe-3 md:ps-6 md:pe-5 py-3 md:py-4 bg-amber-500/5 border-t border-amber-500/20">
            <div className="flex items-start gap-2 mb-3">
              <Smartphone className="text-amber-400 shrink-0 mt-0.5" size={16} />
              <span className="text-xs text-amber-100/70">
                {t("dataSources.enter2faCode")}{" "}
                <span className="text-white font-bold">
                  {humanizeProvider(acc.provider)}
                </span>
              </span>
            </div>
            {/* Input, Verify, then Resend as siblings in this one row —
                e2e locates Resend as the last button in the input's parent. */}
            <div className="flex items-center gap-2 flex-wrap">
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder={t("dataSources.enter2faCodePlaceholder")}
                maxLength={10}
                className="w-24 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-2 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
                value={tfaCode}
                onChange={(e) => onTfaCodeChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitCode();
                }}
              />
              <button
                onClick={submitCode}
                disabled={!tfaCode || tfaIsPending}
                className="px-3 py-2 rounded-lg bg-amber-500 text-black text-xs font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
              >
                {t("dataSources.verify")}
              </button>
              <button
                onClick={onResendTfa}
                disabled={tfaIsPending || resendCooldownRemaining > 0}
                className="px-3 py-2 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {resendCooldownRemaining > 0
                  ? t("dataSources.resendIn", { seconds: resendCooldownRemaining })
                  : t("dataSources.resend")}
              </button>
            </div>
            {!!resendError && (
              <p className="mt-2 text-xs text-red-400 font-medium" dir="auto">
                {resendError}
              </p>
            )}
          </div>
        );
      })()}
    </div>
  );
}
