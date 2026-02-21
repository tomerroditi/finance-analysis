import { useState, useEffect } from "react";
import {
  RefreshCw,
  Smartphone,
  PlayCircle,
  CheckSquare,
  Square,
  CheckCircle2,
  XCircle,
  Info,
  Clock,
  ChevronDown,
} from "lucide-react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { scrapingApi, credentialsApi } from "../../services/api";

interface Account {
  service: string;
  provider: string;
  account_name: string;
}

interface ScraperState {
  process_id: number;
  account: Account;
  status: string; // 'in_progress', 'waiting_for_2fa', 'success', 'failed'
  last_updated: number;
  error_message?: string;
}

interface LastScrapeInfo {
  service: string;
  provider: string;
  account_name: string;
  last_scrape_date: string | null;
}

function isToday(dateString: string): boolean {
  const date = new Date(dateString);
  const today = new Date();
  return (
    date.getFullYear() === today.getFullYear() &&
    date.getMonth() === today.getMonth() &&
    date.getDate() === today.getDate()
  );
}

const SCRAPING_PERIODS = [
  { label: "Auto", days: null },
  { label: "2 Weeks", days: 14 },
  { label: "1 Month", days: 30 },
  { label: "2 Months", days: 60 },
  { label: "3 Months", days: 90 },
  { label: "6 Months", days: 180 },
  { label: "12 Months", days: 365 },
] as const;

function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));

  if (diffDays === 0) return "Today";
  if (diffDays === 1) return "Yesterday";
  if (diffDays < 7) return `${diffDays}d ago`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)}w ago`;
  return date.toLocaleDateString("en-US", { month: "short", day: "numeric" });
}

export function ScrapingWidget() {
  const queryClient = useQueryClient();
  const [tfaCode, setTfaCode] = useState("");
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(
    new Set(),
  );
  const [scrapingPeriodDays, setScrapingPeriodDays] = useState<number | null>(
    null,
  );

  // Map of process_id -> ScraperState
  const [runningScrapers, setRunningScrapers] = useState<
    Record<number, ScraperState>
  >({});

  // Fetch accounts
  const { data: accounts } = useQuery({
    queryKey: ["credentials-accounts"],
    queryFn: () =>
      credentialsApi.getAccounts().then((res) => res.data as Account[]),
  });

  // Fetch last scrape dates
  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes"],
    queryFn: () =>
      scrapingApi.getLastScrapes().then((res) => res.data as LastScrapeInfo[]),
  });

  // Helper to get last scrape info for an account
  const getLastScrapeInfo = (acc: Account): LastScrapeInfo | undefined => {
    return lastScrapes?.find(
      (ls) =>
        ls.service === acc.service &&
        ls.provider === acc.provider &&
        ls.account_name === acc.account_name,
    );
  };

  // Start Scraper Helper
  const startScraper = async (acc: Account) => {
    try {
      const res = await scrapingApi.start({
        service: acc.service,
        provider: acc.provider,
        account: acc.account_name,
        ...(scrapingPeriodDays !== null && {
          scraping_period_days: scrapingPeriodDays,
        }),
      });
      handleScrapeSuccess(res, acc);
    } catch (e) {
      console.error("Failed to start scraper:", e);
    }
  };

  const handleScrapeSuccess = (res: any, acc: Account) => {
    const processId = res.data; // integer
    setRunningScrapers((prev) => ({
      ...prev,
      [processId]: {
        process_id: processId,
        account: acc,
        status: "in_progress",
        last_updated: Date.now(),
      },
    }));
  };

  // 2FA Mutation
  const tfaMutation = useMutation({
    mutationFn: ({
      service,
      provider,
      account,
      code,
    }: {
      service: string;
      provider: string;
      account: string;
      code: string;
    }) => scrapingApi.submit2fa(service, provider, account, code),
    onSuccess: () => {
      setTfaCode("");
    },
  });

  // Polling Effect
  useEffect(() => {
    const checkStatus = async () => {
      const activeScrapers = Object.values(runningScrapers).filter(
        (s) => s.status === "in_progress" || s.status === "waiting_for_2fa",
      );

      if (activeScrapers.length === 0) return;

      for (const scraper of activeScrapers) {
        try {
          const res = await scrapingApi.getStatus(scraper.process_id);
          const newStatus = res.data.status; // 'in_progress', 'waiting_for_2fa', 'success', 'failed'
          const errorMessage = res.data.error_message;

          if (
            newStatus !== scraper.status ||
            Date.now() - scraper.last_updated > 5000
          ) {
            // Invalidate last scrapes query when a scraper completes successfully
            if (newStatus === "success" && scraper.status !== "success") {
              queryClient.invalidateQueries({ queryKey: ["last-scrapes"] });
            }

            setRunningScrapers((prev) => ({
              ...prev,
              [scraper.process_id]: {
                ...scraper,
                status: newStatus,
                error_message: errorMessage,
                last_updated: Date.now(),
              },
            }));
          }
        } catch (e) {
          console.error("Failed to check status for", scraper.process_id, e);
        }
      }
    };

    const interval = setInterval(checkStatus, 2000);
    return () => clearInterval(interval);
  }, [runningScrapers]);

  const activeTfaScraper = Object.values(runningScrapers).find(
    (s) => s.status === "waiting_for_2fa",
  );
  const isRunning = Object.values(runningScrapers).some(
    (s) => s.status === "in_progress",
  );

  const getAccountId = (acc: Account) =>
    `${acc.service}_${acc.provider}_${acc.account_name}`;

  const toggleSelection = (id: string) => {
    const newSet = new Set(selectedAccounts);
    if (newSet.has(id)) newSet.delete(id);
    else newSet.add(id);
    setSelectedAccounts(newSet);
  };

  const handleStartSelected = () => {
    if (selectedAccounts.size === 0) return;
    const selectedList = accounts?.filter((acc) =>
      selectedAccounts.has(getAccountId(acc)),
    );
    selectedList?.forEach((acc) => startScraper(acc));
    setSelectedAccounts(new Set());
  };

  const handleStartSingle = (acc: Account) => {
    startScraper(acc);
  };

  const handleStartAll = () => {
    accounts?.forEach((acc) => startScraper(acc));
  };

  // Helper to get color/icon based on provider
  const getProviderStyle = (provider: string) => {
    const p = provider.toLowerCase();
    if (p.includes("max")) return "bg-blue-500";
    if (p.includes("hapoalim")) return "bg-red-600";
    if (p.includes("visa") || p.includes("cal")) return "bg-emerald-500";
    if (p.includes("mizrahi")) return "bg-orange-500";
    if (p.includes("discount")) return "bg-lime-500";
    if (p.includes("amex")) return "bg-blue-800";
    if (p.includes("onezero")) return "bg-gray-800 border border-white/20";
    // Test Providers
    if (p.includes("test")) return "bg-amber-600/50 border border-amber-500/30";

    return "bg-slate-500";
  };

  const getStatusIcon = (scraper: ScraperState | undefined) => {
    if (!scraper) return <PlayCircle size={16} />;
    if (scraper.status === "in_progress")
      return <RefreshCw size={16} className="animate-spin text-blue-400" />;
    if (scraper.status === "waiting_for_2fa")
      return <Smartphone size={16} className="text-amber-400 animate-pulse" />;
    if (scraper.status === "success")
      return <CheckCircle2 size={16} className="text-emerald-400" />;
    // For failed or any other status, show play icon (retry)
    return <PlayCircle size={16} />;
  };

  // Reverse lookup for display
  const getScraperForAccount = (acc: Account) => {
    // Find the latest scraper for this account
    return Object.values(runningScrapers)
      .filter(
        (s) =>
          s.account.service === acc.service &&
          s.account.provider === acc.provider &&
          s.account.account_name === acc.account_name,
      )
      .sort((a, b) => b.process_id - a.process_id)[0];
  };

  return (
    <div className="bg-[var(--surface)] rounded-2xl p-6 border border-[var(--surface-light)] shadow-xl flex flex-col h-full">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <RefreshCw
            className={`text-[var(--primary)] ${isRunning ? "animate-spin" : ""}`}
            size={24}
          />
          <div>
            <h3 className="text-lg font-bold">Data Import</h3>
            <p className="text-sm text-[var(--text-muted)]">
              Sync financial data
            </p>
          </div>
        </div>
        {isRunning && (
          <span className="text-xs font-bold uppercase tracking-wider text-blue-400 animate-pulse bg-blue-400/10 px-2 py-1 rounded-full border border-blue-400/20">
            Running
          </span>
        )}
      </div>

      <div className="space-y-6 flex-1 flex flex-col">
        {/* 2FA Input Area */}
        {activeTfaScraper && (
          <div className="p-4 rounded-xl bg-amber-500/10 border border-amber-500/30 animate-in zoom-in-95 duration-300">
            <div className="flex items-center gap-3 mb-4">
              <Smartphone className="text-amber-400" size={20} />
              <div>
                <h4 className="text-sm font-bold text-white">2FA Required</h4>
                <p className="text-xs text-amber-100/70">
                  Code for{" "}
                  <span className="text-white font-bold">
                    {activeTfaScraper.account.provider} (
                    {activeTfaScraper.account.account_name})
                  </span>
                </p>
              </div>
            </div>
            <div className="flex flex-wrap gap-2">
              <input
                type="text"
                placeholder="Code"
                maxLength={10}
                className="flex-1 min-w-0 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-2 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
                value={tfaCode}
                onChange={(e) => setTfaCode(e.target.value)}
              />
              <button
                onClick={() => {
                  // Optimistic update: Mark as in_progress immediately
                  setRunningScrapers((prev) => ({
                    ...prev,
                    [activeTfaScraper.process_id]: {
                      ...activeTfaScraper,
                      status: "in_progress",
                      last_updated: Date.now(),
                    },
                  }));

                  tfaMutation.mutate({
                    service: activeTfaScraper.account.service,
                    provider: activeTfaScraper.account.provider,
                    account: activeTfaScraper.account.account_name,
                    code: tfaCode,
                  });
                }}
                disabled={!tfaCode || tfaMutation.isPending}
                className="px-3 py-2 rounded-lg bg-amber-500 text-black text-xs font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
              >
                Verify
              </button>
              <button
                onClick={async () => {
                  if (!activeTfaScraper) return;

                  // Optimistic update: Mark old one as canceled/reset immediately in UI
                  setRunningScrapers((prev) => {
                    const newState = { ...prev };
                    delete newState[activeTfaScraper.process_id]; // Remove old one or mark canceled
                    return newState;
                  });

                  try {
                    await scrapingApi.abort(activeTfaScraper.process_id);
                    // Start new one
                    startScraper(activeTfaScraper.account);
                  } catch (e) {
                    console.error("Failed to resend code:", e);
                    // Revert state if needed, or just let the error log
                  }
                }}
                disabled={tfaMutation.isPending}
                className="px-3 py-2 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50"
              >
                Resend
              </button>
            </div>
          </div>
        )}

        {/* Service Selection */}
        <div className="space-y-3 flex-1 overflow-y-auto custom-scrollbar pr-1">
          <div className="flex gap-2 mb-2">
            <div className="relative">
              <select
                value={scrapingPeriodDays ?? "auto"}
                onChange={(e) =>
                  setScrapingPeriodDays(
                    e.target.value === "auto" ? null : Number(e.target.value),
                  )
                }
                disabled={isRunning}
                className="appearance-none bg-[var(--surface-light)] border border-[var(--surface-light)] rounded-xl px-3 pr-7 py-2.5 text-xs font-bold text-white outline-none focus:border-[var(--primary)]/50 transition-colors disabled:opacity-50 cursor-pointer h-full"
              >
                {SCRAPING_PERIODS.map((p) => (
                  <option key={p.label} value={p.days ?? "auto"}>
                    {p.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={12}
                className="absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none"
              />
            </div>
            <button
              onClick={handleStartAll}
              disabled={isRunning}
              className="flex-1 py-2.5 rounded-xl bg-[var(--primary)] text-white text-xs font-bold hover:bg-[var(--primary-dark)] shadow-lg shadow-[var(--primary)]/20 transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              <PlayCircle size={16} />
              Scrape All
            </button>
            {selectedAccounts.size > 0 && (
              <button
                onClick={handleStartSelected}
                disabled={isRunning}
                className="flex-1 py-2.5 rounded-xl bg-[var(--surface-light)] text-white text-xs font-bold hover:bg-[var(--surface-base)] transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                <PlayCircle size={16} />
                Start Selected ({selectedAccounts.size})
              </button>
            )}
          </div>

          <div className="grid grid-cols-1 gap-2">
            {accounts?.map((acc) => {
              const id = getAccountId(acc);
              const isSelected = selectedAccounts.has(id);
              const scraper = getScraperForAccount(acc);
              const active =
                scraper &&
                (scraper.status === "in_progress" ||
                  scraper.status === "waiting_for_2fa");

              return (
                <div
                  key={id}
                  className={`flex items-center justify-between p-3 rounded-xl border border-[var(--surface-light)] bg-[var(--surface-base)]/50 hover:bg-[var(--surface-light)]/20 transition-all group ${isSelected ? "border-[var(--primary)]/50 bg-[var(--primary)]/5" : ""}`}
                >
                  <div
                    className="flex items-center gap-3 overflow-hidden flex-1 cursor-pointer"
                    onClick={() => toggleSelection(id)}
                  >
                    <div
                      className={`text-[var(--text-muted)] group-hover:text-white transition-colors`}
                    >
                      {isSelected ? (
                        <CheckSquare
                          size={18}
                          className="text-[var(--primary)]"
                        />
                      ) : (
                        <Square size={18} />
                      )}
                    </div>
                    <div className="flex items-center gap-2 overflow-hidden">
                      <div
                        className={`w-1.5 h-6 rounded-full shrink-0 ${getProviderStyle(acc.provider)}`}
                      />
                      <div className="flex flex-col truncate">
                        <span className="font-bold text-xs truncate capitalize">
                          {acc.provider.replace("_", " ")}
                        </span>
                        <span className="text-[10px] text-[var(--text-muted)] truncate">
                          {acc.account_name}
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {/* Status with error tooltip for failed */}
                    {scraper && scraper.status === "failed" && (
                      <div className="flex items-center gap-1">
                        <span className="text-[10px] font-bold uppercase text-red-400">
                          failed
                        </span>
                        {scraper.error_message && (
                          <div className="relative group">
                            <Info
                              size={12}
                              className="text-red-400 cursor-help"
                            />
                            <div className="absolute bottom-full right-0 mb-1 hidden group-hover:block z-50">
                              <div className="bg-gray-900 text-white text-[9px] p-2 rounded shadow-lg max-w-[200px] whitespace-normal border border-gray-700">
                                {scraper.error_message}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {scraper && scraper.status === "success" && (
                      <span className="text-[10px] font-bold uppercase text-emerald-400">
                        success
                      </span>
                    )}

                    {/* Last scrape status - show when no active session status */}
                    {(!scraper ||
                      (scraper.status !== "in_progress" &&
                        scraper.status !== "waiting_for_2fa" &&
                        scraper.status !== "success" &&
                        scraper.status !== "failed")) &&
                      (() => {
                        const lastScrape = getLastScrapeInfo(acc);
                        if (!lastScrape?.last_scrape_date) {
                          return (
                            <span className="text-[10px] text-[var(--text-muted)] italic">
                              Never synced
                            </span>
                          );
                        }
                        const scrapedToday = isToday(
                          lastScrape.last_scrape_date,
                        );
                        if (scrapedToday) {
                          return (
                            <div className="flex items-center gap-1 px-1.5 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                              <CheckCircle2
                                size={10}
                                className="text-emerald-400"
                              />
                              <span className="text-[9px] font-semibold text-emerald-400">
                                Synced
                              </span>
                            </div>
                          );
                        }
                        return (
                          <div className="flex items-center gap-1 text-[var(--text-muted)]">
                            <Clock size={10} />
                            <span className="text-[9px]">
                              {formatRelativeDate(lastScrape.last_scrape_date)}
                            </span>
                          </div>
                        );
                      })()}

                    {/* Abort button for running scrapers */}
                    {active && (
                      <button
                        onClick={async (e) => {
                          e.stopPropagation();
                          try {
                            await scrapingApi.abort(scraper!.process_id);
                            setRunningScrapers((prev) => ({
                              ...prev,
                              [scraper!.process_id]: {
                                ...scraper!,
                                status: "failed",
                                error_message: "Aborted by user",
                                last_updated: Date.now(),
                              },
                            }));
                          } catch (err) {
                            console.error("Failed to abort:", err);
                          }
                        }}
                        className="p-1 rounded hover:bg-red-500/20 text-red-400 hover:text-red-300 transition-colors"
                        title="Abort"
                      >
                        <XCircle size={14} />
                      </button>
                    )}

                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleStartSingle(acc);
                      }}
                      disabled={active}
                      className={`p-1.5 rounded-lg hover:bg-[var(--primary)]/10 text-[var(--text-muted)] hover:text-[var(--primary)] transition-colors ${active ? "opacity-100" : "opacity-0 group-hover:opacity-100"} disabled:opacity-50`}
                      title="Scrape this source only"
                    >
                      {getStatusIcon(scraper)}
                    </button>
                  </div>
                </div>
              );
            })}
            {(!accounts || accounts.length === 0) && (
              <div className="text-center p-4 text-[var(--text-muted)] text-xs">
                No configured data sources found.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
