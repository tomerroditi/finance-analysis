import { useState, useEffect } from "react";
import {
  RefreshCw,
  Smartphone,
  AlertCircle,
  PlayCircle,
  CheckSquare,
  Square,
  CheckCircle2,
  XCircle,
} from "lucide-react";
import { useQuery, useMutation } from "@tanstack/react-query";
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
}

export function ScrapingWidget() {
  const [tfaCode, setTfaCode] = useState("");
  const [selectedAccounts, setSelectedAccounts] = useState<Set<string>>(
    new Set(),
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

  // Start Mutation
  const startMutation = useMutation({
    mutationFn: (acc: Account) =>
      scrapingApi.start({
        service: acc.service,
        provider: acc.provider,
        account: acc.account_name,
      }),
    onSuccess: (res, acc) => {
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
    },
  });

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

          if (
            newStatus !== scraper.status ||
            Date.now() - scraper.last_updated > 5000
          ) {
            setRunningScrapers((prev) => ({
              ...prev,
              [scraper.process_id]: {
                ...scraper,
                status: newStatus,
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
    selectedList?.forEach((acc) => startMutation.mutate(acc));
    setSelectedAccounts(new Set());
  };

  const handleStartSingle = (acc: Account) => {
    startMutation.mutate(acc);
  };

  const handleStartAll = () => {
    accounts?.forEach((acc) => startMutation.mutate(acc));
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
    if (scraper.status === "failed")
      return <XCircle size={16} className="text-red-400" />;
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
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="Code"
                maxLength={10}
                className="flex-1 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-2 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
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
                    startMutation.mutate(activeTfaScraper.account);
                  } catch (e) {
                    console.error("Failed to resend code:", e);
                    // Revert state if needed, or just let the error log
                  }
                }}
                disabled={tfaMutation.isPending || startMutation.isPending}
                className="px-3 py-2 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50"
              >
                Resend
              </button>
            </div>
          </div>
        )}

        {/* Service Selection */}
        <div className="space-y-3 flex-1 overflow-y-auto max-h-[300px] custom-scrollbar pr-1">
          <div className="flex gap-2 mb-2">
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
                    {/* Status Indicator */}
                    {scraper &&
                      scraper.status !== "in_progress" &&
                      scraper.status !== "waiting_for_2fa" && (
                        <span
                          className={`text-[10px] font-bold uppercase ${scraper.status === "success" ? "text-emerald-400" : "text-red-400"}`}
                        >
                          {scraper.status}
                        </span>
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

        {/* Logs/Status Summary */}
        {Object.keys(runningScrapers).length > 0 && (
          <div className="space-y-2 pt-4 border-t border-[var(--surface-light)] mt-auto">
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold uppercase tracking-widest text-[var(--text-muted)]">
                Recent Activity
              </h4>
            </div>
            <div className="max-h-[120px] overflow-y-auto space-y-1 pr-1 custom-scrollbar">
              {Object.values(
                Object.values(runningScrapers).reduce(
                  (acc, scraper) => {
                    // Deduplicate: Keep only the latest processId per account
                    const key = `${scraper.account.service}_${scraper.account.provider}_${scraper.account.account_name}`;
                    if (!acc[key] || acc[key].process_id < scraper.process_id) {
                      acc[key] = scraper;
                    }
                    return acc;
                  },
                  {} as Record<string, ScraperState>,
                ),
              )
                .sort((a, b) => b.last_updated - a.last_updated)
                .map((scraper) => (
                  <div
                    key={scraper.process_id}
                    className="flex items-center justify-between p-2 rounded bg-black/20 text-[10px]"
                  >
                    <span className="font-bold uppercase tracking-tight truncate mr-2">
                      {scraper.account.provider}{" "}
                      <span className="text-[var(--text-muted)]">
                        / {scraper.account.account_name}
                      </span>
                    </span>
                    <div className="flex items-center gap-1 shrink-0">
                      {scraper.status === "success" ? (
                        <div className="flex items-center gap-1 text-emerald-400">
                          <CheckCircle2 size={10} />
                          <span className="font-medium">Success</span>
                        </div>
                      ) : scraper.status === "failed" ? (
                        <div className="flex items-center gap-1 text-red-400">
                          <AlertCircle size={10} />
                          <span>Failed</span>
                        </div>
                      ) : (
                        <div className="flex items-center gap-1 text-blue-400">
                          <RefreshCw size={10} className="animate-spin" />
                          <span>Running</span>
                        </div>
                      )}
                    </div>
                  </div>
                ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
