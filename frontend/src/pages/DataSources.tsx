import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Globe,
  RefreshCw,
  ChevronDown,
  Landmark,
  CreditCard,
  Shield,
} from "lucide-react";
import {
  credentialsApi,
  bankBalancesApi,
  scrapingApi,
} from "../services/api";
import type { BankBalance, CredentialAccount } from "../services/api";

import { accountKey, isScraperActive, useScraping } from "../hooks/useScraping";
import { Skeleton } from "../components/common/Skeleton";
import { EmptyState } from "../components/common/EmptyState";
import { UpdateBankBalanceModal } from "../components/modals/UpdateBankBalanceModal";
import { AccountCard } from "../components/dataSources/AccountCard";
import { SourcesSummary } from "../components/dataSources/SourcesSummary";
import {
  ConnectAccountModal,
  type ConnectModalMode,
} from "../components/dataSources/ConnectAccountModal";
import { DisconnectAccountModal } from "../components/dataSources/DisconnectAccountModal";
import { needsAttention, sourceHealth } from "../components/dataSources/sourceHealth";
import { useNotify } from "../context/DialogContext";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";

const SCRAPING_PERIODS = [
  { key: "auto", days: null },
  { key: "weeks2", days: 14 },
  { key: "month1", days: 30 },
  { key: "months2", days: 60 },
  { key: "months3", days: 90 },
  { key: "months6", days: 180 },
  { key: "months12", days: 365 },
] as const;

/**
 * Service sections, in the order they're listed. Icons and accent colours match
 * the connect-account service chooser and each card's accent stripe, so a
 * source keeps the same visual identity from the moment it's added.
 */
const SERVICE_SECTIONS = [
  {
    service: "banks",
    icon: Landmark,
    iconClass: "bg-blue-500/10 text-blue-400",
    titleKey: "dataSources.bankAccounts",
  },
  {
    service: "credit_cards",
    icon: CreditCard,
    iconClass: "bg-purple-500/10 text-purple-400",
    titleKey: "dataSources.creditCards",
  },
  {
    service: "insurances",
    icon: Shield,
    iconClass: "bg-emerald-500/10 text-emerald-400",
    titleKey: "dataSources.insurance",
  },
] as const;

export function DataSources() {
  const { t } = useTranslation();
  const qk = useQueryKeys();
  const queryClient = useQueryClient();
  const notify = useNotify();

  const [modal, setModal] = useState<{
    mode: ConnectModalMode;
    account: CredentialAccount | null;
  } | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<CredentialAccount | null>(null);
  const [scrapingPeriodDays, setScrapingPeriodDays] = useState<number | null>(null);
  const [balanceModalAccount, setBalanceModalAccount] = useState<
    { provider: string; account_name: string; balance: number | null } | null
  >(null);

  const {
    startScraper, scrapeAll, submitTfa, resendTfa, abortScraper,
    getScraperForAccount, isStartPending, isTfaPending, isAnyScraping,
    activeScraperCount, resendCooldownRemaining, resendErrors, tfaCodes,
    setTfaCode,
  } = useScraping();

  const { data: accounts, isLoading } = useQuery({
    queryKey: qk.credentials.accounts(),
    queryFn: () => credentialsApi.getAccounts().then((res) => res.data),
  });

  const { data: bankBalances } = useQuery({
    queryKey: qk.balances.bank(),
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: lastScrapes } = useQuery({
    queryKey: qk.scraping.lastScrapes(),
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
  });

  const deleteMutation = useMutation({
    mutationFn: ({
      acc,
      deleteData,
    }: {
      acc: CredentialAccount;
      deleteData: boolean;
    }) =>
      credentialsApi
        .delete(acc.service, acc.provider, acc.account_name, { deleteData })
        .then((res) => res.data),
    onSuccess: (result, { deleteData }) => {
      queryClient.invalidateQueries({ queryKey: qkPrefix.credentialsAccounts });
      if (deleteData) {
        // Wiping an account's data changes far more than the accounts list:
        // its transactions (plus splits/refunds/notes/overrides), its bank
        // balance (and the prior wealth derived from it) and its scrape
        // history are all gone. Narrow prefixes only — no blanket sweep.
        queryClient.invalidateQueries({ queryKey: qkPrefix.transactions });
        queryClient.invalidateQueries({ queryKey: qkPrefix.pendingRefunds });
        queryClient.invalidateQueries({ queryKey: qkPrefix.budget });
        queryClient.invalidateQueries({ queryKey: qkPrefix.analytics });
        queryClient.invalidateQueries({ queryKey: qkPrefix.bankBalances });
        queryClient.invalidateQueries({ queryKey: qkPrefix.lastScrapes });
      }
      setDeleteTarget(null);
      const deleted = result?.transactions_deleted ?? 0;
      if (deleted > 0) {
        notify.success(
          t("dataSources.transactionsDeleted", { count: deleted }),
        );
      }
    },
    onError: () => {
      setDeleteTarget(null);
      notify.error(t("dataSources.disconnectFailed"));
    },
  });

  const getAccountBalance = (
    provider: string,
    accountName: string,
  ): BankBalance | undefined =>
    bankBalances?.find(
      (b) => b.provider === provider && b.account_name === accountName,
    );

  const lastScrapeFor = (acc: CredentialAccount): string | null =>
    lastScrapes?.find(
      (s) =>
        s.service === acc.service &&
        s.provider === acc.provider &&
        s.account_name === acc.account_name,
    )?.last_scrape_date ?? null;

  const isScrapedToday = (provider: string, accountName: string): boolean => {
    const scrape = lastScrapes?.find(
      (s) => s.provider === provider && s.account_name === accountName,
    );
    return sourceHealth(scrape?.last_scrape_date ?? null) === "today";
  };

  // The accounts "Scrape All" will actually launch. Two exclusions:
  //  - already scraping (`scrapeAll` re-checks this itself, so a stale render
  //    can't double-launch);
  //  - already synced today — a same-day re-run re-fetches a window the
  //    account already has, and on a 2FA provider it costs another SMS.
  // A single source can still be re-scraped from its own card button: that's
  // an explicit per-account decision (e.g. after widening the period), which
  // is exactly what a bulk "scrape everything" action shouldn't assume.
  const scrapeAllTargets = (accounts ?? []).filter((acc: CredentialAccount) => {
    if (isScrapedToday(acc.provider, acc.account_name)) return false;
    const scraper = getScraperForAccount(acc);
    return !scraper || !isScraperActive(scraper);
  });

  const syncedTodayCount = (accounts ?? []).filter((acc: CredentialAccount) =>
    isScrapedToday(acc.provider, acc.account_name),
  ).length;
  const needsAttentionCount = (accounts ?? []).filter((acc: CredentialAccount) =>
    needsAttention(lastScrapeFor(acc)),
  ).length;

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-8">
        <Skeleton variant="text" lines={1} className="w-48 md:w-64" />
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 md:gap-4">
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
          <Skeleton variant="card" className="h-24" />
        </div>
        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
          <Skeleton variant="card" className="h-48" />
          <Skeleton variant="card" className="h-48" />
        </div>
      </div>
    );

  const hasAccounts = (accounts?.length ?? 0) > 0;

  const renderAccountCard = (acc: CredentialAccount) => {
    const scraper = getScraperForAccount(acc);
    // Same key the store uses, so a half-typed code survives navigating
    // away and back.
    const tfaKey = accountKey(acc);
    const bal = getAccountBalance(acc.provider, acc.account_name);

    return (
      <AccountCard
        key={tfaKey}
        acc={acc}
        scraper={scraper}
        lastScrapeDate={lastScrapeFor(acc)}
        balance={bal}
        scrapedToday={isScrapedToday(acc.provider, acc.account_name)}
        isStartPending={isStartPending(acc)}
        tfaIsPending={isTfaPending(acc)}
        tfaCode={tfaCodes[tfaKey] || ""}
        onTfaCodeChange={(code) => setTfaCode(tfaKey, code)}
        onSubmitTfa={(code) => {
          submitTfa(scraper!, code);
          setTfaCode(tfaKey, "");
        }}
        onResendTfa={() => resendTfa(scraper!)}
        resendCooldownRemaining={
          scraper ? resendCooldownRemaining(scraper.process_id) : 0
        }
        resendErrorInfo={scraper ? resendErrors[scraper.process_id] : undefined}
        onStartScrape={(opts) => startScraper(acc, scrapingPeriodDays, opts)}
        onAbortScrape={() => abortScraper(scraper!)}
        onOpenBalanceModal={() =>
          setBalanceModalAccount({
            provider: acc.provider,
            account_name: acc.account_name,
            balance: bal ? bal.balance : null,
          })
        }
        onView={() => setModal({ mode: "view", account: acc })}
        onEdit={() => setModal({ mode: "edit", account: acc })}
        onDelete={() => setDeleteTarget(acc)}
      />
    );
  };

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500 pb-20">
      {/* Toolbar */}
      <div className="flex flex-wrap items-center justify-end gap-2 md:gap-3">
        <div className="relative">
          <select
            value={scrapingPeriodDays ?? "auto"}
            onChange={(e) =>
              setScrapingPeriodDays(
                e.target.value === "auto" ? null : Number(e.target.value),
              )
            }
            // Stays usable while scrapes run: the period is read when a
            // scrape STARTS, so changing it only affects the next launch —
            // and with parallel scraping there is almost always one running.
            aria-label={t("dataSources.scrapePeriodLabel")}
            className="appearance-none bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl px-3 pe-7 py-2.5 text-xs font-bold text-white outline-none focus:border-[var(--primary)]/50 transition-colors cursor-pointer"
          >
            {SCRAPING_PERIODS.map((p) => (
              <option key={p.key} value={p.days ?? "auto"}>
                {t(`dataSources.scrapePeriod.${p.key}`)}
              </option>
            ))}
          </select>
          <ChevronDown
            size={12}
            className="absolute end-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
          />
        </div>
        <button
          // Stays clickable while scrapes are running — it launches whatever
          // is still eligible, in parallel, so this is how a user picks up
          // sources they added (or that failed) mid-run. Disabled only when
          // nothing is eligible at all.
          onClick={() => scrapeAll(scrapeAllTargets, scrapingPeriodDays)}
          disabled={!scrapeAllTargets.length}
          title={
            hasAccounts && !scrapeAllTargets.length
              ? t("dataSources.scrapeAllNothingToDo")
              : undefined
          }
          className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] text-white rounded-xl font-bold hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <RefreshCw size={16} className={isAnyScraping ? "animate-spin" : ""} />
          {isAnyScraping
            ? t("dataSources.scrapeAllRunning", { count: activeScraperCount })
            : t("dataSources.scrapeAll")}
        </button>
        <button
          onClick={() => setModal({ mode: "create", account: null })}
          className="flex flex-1 sm:flex-none items-center justify-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20"
        >
          <Plus size={18} /> {t("dataSources.connectAccount")}
        </button>
      </div>

      {!hasAccounts ? (
        <EmptyState
          icon={Globe}
          title={t("dataSources.noAccountsConnected")}
          description={t("dataSources.noAccountsDesc")}
          steps={[
            {
              title: t("emptyStates.connectStep.title"),
              description: t("emptyStates.connectStep.description"),
            },
            {
              title: t("emptyStates.scrapeStep.title"),
              description: t("emptyStates.scrapeStep.description"),
            },
            {
              title: t("emptyStates.analyseStep.title"),
              description: t("emptyStates.analyseStep.description"),
            },
          ]}
          cta={{
            label: t("dataSources.connectFirstAccount"),
            onClick: () => setModal({ mode: "create", account: null }),
          }}
        />
      ) : (
        <>
          <SourcesSummary
            total={accounts?.length ?? 0}
            syncedToday={syncedTodayCount}
            needsAttention={needsAttentionCount}
          />

          <div className="space-y-6 md:space-y-8">
            {SERVICE_SECTIONS.map(({ service, icon: Icon, iconClass, titleKey }) => {
              const sectionAccounts =
                accounts?.filter((a: CredentialAccount) => a.service === service) ?? [];
              if (sectionAccounts.length === 0) return null;
              return (
                <section key={service}>
                  <div className="flex items-center gap-2 mb-3 md:mb-4">
                    <span className={`p-1.5 rounded-lg ${iconClass}`}>
                      <Icon size={16} />
                    </span>
                    <h2 className="text-lg md:text-xl font-bold">{t(titleKey)}</h2>
                    <span className="text-[10px] font-black bg-[var(--primary)]/20 text-[var(--primary)] px-2 py-0.5 rounded-full">
                      {sectionAccounts.length}
                    </span>
                  </div>
                  {/* items-start: a card with its 2FA prompt open is much
                      taller, and stretching its row-mate to match left a dead
                      gap under the shorter card's actions. */}
                  <div className="grid grid-cols-1 xl:grid-cols-2 gap-4 md:gap-5 items-start">
                    {sectionAccounts.map(renderAccountCard)}
                  </div>
                </section>
              );
            })}
          </div>
        </>
      )}

      {/* Keyed by target so the wizard always starts fresh, and unmounted on
          close so no stale form state can leak into the next open. */}
      <ConnectAccountModal
        key={
          modal
            ? `${modal.mode}-${modal.account ? accountKey(modal.account) : "new"}`
            : "closed"
        }
        mode={modal?.mode ?? null}
        account={modal?.account ?? null}
        onClose={() => setModal(null)}
      />

      {/* Keyed by target so the keep-vs-delete choice resets to the safe
          default every time the modal opens for a different account. */}
      <DisconnectAccountModal
        key={
          deleteTarget ? accountKey(deleteTarget) : "no-disconnect-target"
        }
        isOpen={deleteTarget !== null}
        accountName={deleteTarget?.account_name ?? ""}
        isPending={deleteMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={(deleteData) => {
          if (deleteTarget) deleteMutation.mutate({ acc: deleteTarget, deleteData });
        }}
      />

      <UpdateBankBalanceModal
        isOpen={balanceModalAccount !== null}
        onClose={() => setBalanceModalAccount(null)}
        provider={balanceModalAccount?.provider ?? ""}
        accountName={balanceModalAccount?.account_name ?? ""}
        currentBalance={balanceModalAccount?.balance ?? null}
        isScrapedToday={
          balanceModalAccount
            ? isScrapedToday(
                balanceModalAccount.provider,
                balanceModalAccount.account_name,
              )
            : false
        }
      />
    </div>
  );
}
