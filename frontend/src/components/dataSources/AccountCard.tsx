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
  Clock,
} from "lucide-react";
import type { BankBalance, CredentialAccount } from "../../services/api";
import type { ResendError, ScraperState } from "../../hooks/useScraping";
import { useConfirm } from "../../context/DialogContext";
import { ProviderLogo } from "../common/ProviderLogo";
import { ScrapeErrorTooltip } from "../common/ScrapeErrorTooltip";
import { humanizeAccountType, humanizeProvider } from "../../utils/textFormatting";
import { formatRelativeDate } from "../../utils/dateFormatting";
import { formatCurrency } from "../../utils/numberFormatting";

interface AccountCardProps {
  acc: CredentialAccount;
  scraper: ScraperState | undefined;
  lastScrapeDate: string | null | undefined;
  balance: BankBalance | undefined;
  /** Whether this account was scraped today (gates balance entry + badge). */
  scrapedToday: boolean;
  isAnyScraping: boolean;
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
  onDelete: () => void;
}

/** One connected-account row on the Data Sources page: provider identity,
 * bank balance chip, scraping status/actions, and the inline 2FA section. */
export function AccountCard({
  acc,
  scraper,
  lastScrapeDate,
  balance,
  scrapedToday,
  isAnyScraping,
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
  const confirm = useConfirm();
  const isActive =
    scraper && (scraper.status === "in_progress" || scraper.status === "waiting_for_2fa");

  const submitCode = () => {
    if (tfaCode) onSubmitTfa(tfaCode);
  };

  return (
    <div className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-3 md:p-5 hover:border-[var(--primary)]/30 hover:shadow-xl transition-all">
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-0">
      <div className="flex items-center gap-3 md:gap-5">
        <div className="w-14 h-14 shrink-0 rounded-2xl bg-white flex items-center justify-center p-2 text-gray-700">
          <ProviderLogo
            provider={acc.provider}
            service={acc.service}
            size={40}
            alt={humanizeProvider(acc.provider)}
          />
        </div>
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <h3 className="font-bold text-lg text-white capitalize">
              {acc.account_name}
            </h3>
            <span className="text-[10px] font-black uppercase tracking-widest px-2 py-0.5 rounded bg-[var(--surface-light)] text-[var(--text-muted)]">
              {humanizeProvider(acc.provider)}
            </span>
          </div>
          <p className="text-sm text-[var(--text-muted)] font-medium">
            {humanizeAccountType(acc.service)}
          </p>
        </div>
      </div>
      <div className="flex flex-wrap items-center gap-3 md:gap-4">
        <div className="md:w-[160px] flex items-center md:justify-end">
        {acc.service === "banks" && (
          <div className="flex items-center gap-2">
            {balance ? (
              <span className="text-sm font-semibold text-amber-400">
                {formatCurrency(balance.balance)}
              </span>
            ) : (
              <span className="text-xs text-[var(--text-muted)] italic">
                {t("dataSources.noBalanceSet")}
              </span>
            )}
            <button
              onClick={onOpenBalanceModal}
              disabled={!scrapedToday}
              className={`p-1.5 rounded-lg transition-all ${
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
          </div>
        )}
        </div>

        {/* Scraping Status */}
        <div className="flex items-center gap-2 min-w-[100px] justify-end">
          {scraper?.status === "in_progress" && (
            <div className="flex items-center gap-1.5">
              <RefreshCw size={14} className="animate-spin text-blue-400 shrink-0" />
              <span className="text-xs font-semibold text-blue-400">
                {t("dataSources.scraping")}
              </span>
            </div>
          )}
          {scraper?.status === "waiting_for_2fa" && (
            <div className="flex items-center gap-1.5">
              <Smartphone size={14} className="text-amber-400 animate-pulse" />
              <span className="text-xs font-semibold text-amber-400">{t("dataSources.tfaRequired")}</span>
            </div>
          )}
          {scraper?.status === "success" && (
            <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
              <CheckCircle2 size={12} className="text-emerald-400" />
              <span className="text-[10px] font-semibold text-emerald-400">{t("dataSources.synced")}</span>
            </div>
          )}
          {scraper?.status === "failed" && (
            <div className="flex items-center gap-1.5">
              <span className="text-xs font-semibold text-red-400">{t("dataSources.failed")}</span>
              {!!scraper.error_message && (
                <ScrapeErrorTooltip message={scraper.error_message} />
              )}
            </div>
          )}
          {(!scraper || !["in_progress", "waiting_for_2fa", "success", "failed"].includes(scraper.status)) && (
            <>
              {!lastScrapeDate ? (
                <span className="text-[10px] text-[var(--text-muted)] italic">{t("dataSources.neverSynced")}</span>
              ) : scrapedToday ? (
                <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                  <CheckCircle2 size={12} className="text-emerald-400" />
                  <span className="text-[10px] font-semibold text-emerald-400">{t("dataSources.synced")}</span>
                </div>
              ) : (
                <div className="flex items-center gap-1 text-[var(--text-muted)]">
                  <Clock size={12} />
                  <span className="text-[10px]">{formatRelativeDate(lastScrapeDate)}</span>
                </div>
              )}
            </>
          )}
        </div>

        <div className="flex gap-2">
          {/* Scrape / Abort Button */}
          {isActive ? (
            <button
              onClick={onAbortScrape}
              className="p-2.5 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300 transition-all"
              title={t("dataSources.abortScraping")}
            >
              <XCircle size={20} />
            </button>
          ) : (
            <button
              onClick={() => onStartScrape()}
              disabled={isAnyScraping}
              className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              title={t("dataSources.scrapeThisSource")}
            >
              <PlayCircle size={20} />
            </button>
          )}
          {acc.provider === "onezero" && (
            <button
              onClick={() => onStartScrape({ force2fa: true })}
              disabled={isAnyScraping}
              className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-amber-400 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
              title={t("dataSources.forceTfaTitle")}
              aria-label={t("dataSources.forceTfa")}
            >
              <span className="relative inline-flex">
                <Smartphone size={20} />
                <RefreshCw
                  size={11}
                  className="absolute -bottom-1 -end-1.5 rounded-full bg-[var(--surface-light)] p-[1px] text-amber-400"
                />
              </span>
            </button>
          )}
          <button
            onClick={onView}
            className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
            title={t("dataSources.viewDetails")}
          >
            <Eye size={20} />
          </button>
          <button
            onClick={onEdit}
            className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all"
            title={t("dataSources.editAccount")}
          >
            <Edit2 size={20} />
          </button>
          <button
            onClick={async () => {
              const ok = await confirm({
                title: t("dataSources.disconnectAccount"),
                message: t("dataSources.confirmDisconnect", { name: acc.account_name }),
                confirmLabel: t("dataSources.disconnectAccount"),
                isDestructive: true,
              });
              if (ok) onDelete();
            }}
            className="p-2.5 rounded-xl bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-all"
            title={t("dataSources.disconnectAccount")}
          >
            <Trash2 size={20} />
          </button>
        </div>
      </div>
      </div>

      {/* 2FA Inline Section */}
      {scraper?.status === "waiting_for_2fa" && (() => {
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
        <div className="mt-3 md:mt-4 pt-3 md:pt-4 border-t border-amber-500/20">
          <div className="flex flex-col md:flex-row items-start md:items-center gap-3">
            <Smartphone className="text-amber-400 shrink-0" size={18} />
            <span className="text-xs text-amber-100/70">
              {t("dataSources.enter2faCode")} <span className="text-white font-bold">{humanizeProvider(acc.provider)}</span>
            </span>
            <div className="flex items-center gap-2 ms-auto">
              <input
                type="text"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder={t("dataSources.enter2faCodePlaceholder")}
                maxLength={10}
                className="w-28 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-1.5 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
                value={tfaCode}
                onChange={(e) => onTfaCodeChange(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") submitCode();
                }}
              />
              <button
                onClick={submitCode}
                disabled={!tfaCode || tfaIsPending}
                className="px-3 py-1.5 rounded-lg bg-amber-500 text-black text-xs font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
              >
                {t("dataSources.verify")}
              </button>
              <button
                onClick={onResendTfa}
                disabled={tfaIsPending || resendCooldownRemaining > 0}
                className="px-3 py-1.5 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
              >
                {resendCooldownRemaining > 0
                  ? t("dataSources.resendIn", { seconds: resendCooldownRemaining })
                  : t("dataSources.resend")}
              </button>
            </div>
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
