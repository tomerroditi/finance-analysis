import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../hooks/useScrollLock";
import {
  Plus,
  Trash2,
  Globe,
  Landmark,
  CreditCard,
  ChevronRight,
  X,
  AlertCircle,
  Edit2,
  Eye,
  EyeOff,
  DollarSign,
  Check,
  RefreshCw,
  PlayCircle,
  ChevronDown,
  Smartphone,
  XCircle,
  Info,
  CheckCircle2,
  Clock,
  Shield,
} from "lucide-react";
import {
  credentialsApi,
  bankBalancesApi,
  scrapingApi,
} from "../services/api";
import type { BankBalance } from "../services/api";

import { useDemoMode } from "../context/DemoModeContext";
import { useScraping } from "../hooks/useScraping";
import { Skeleton } from "../components/common/Skeleton";
import { humanizeAccountType, humanizeProvider } from "../utils/textFormatting";
import { formatShortDate } from "../utils/dateFormatting";
import { formatCurrency } from "../utils/numberFormatting";
import i18n from "../i18n";

function formatRelativeDate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays === 0) return i18n.t("common.today");
  if (diffDays === 1) return i18n.t("common.yesterday");
  if (diffDays < 7) return `${diffDays} ${i18n.t("common.daysAgo")}`;
  if (diffDays < 30) return `${Math.floor(diffDays / 7)} ${i18n.t("common.weeksAgo")}`;
  return formatShortDate(date);
}

const SCRAPING_PERIODS = [
  { key: "auto", days: null },
  { key: "weeks2", days: 14 },
  { key: "month1", days: 30 },
  { key: "months2", days: 60 },
  { key: "months3", days: 90 },
  { key: "months6", days: 180 },
  { key: "months12", days: 365 },
] as const;

interface CredentialAccount {
  service: string;
  provider: string;
  account_name: string;
}

export function DataSources() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [selectedService, setSelectedService] = useState<
    "banks" | "credit_cards" | "insurances" | ""
  >("");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [accountName, setAccountName] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [formFields, setFormFields] = useState<string[]>([]);
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>(
    {},
  );
  const [editingAccount, setEditingAccount] = useState<CredentialAccount | null>(null);
  const [isViewOnly, setIsViewOnly] = useState(false);
  useScrollLock(isAddOpen || !!editingAccount);

  const {
    startScraper, scrapeAll, submitTfa, resendTfa, abortScraper,
    getScraperForAccount, isAnyScraping, tfaIsPending,
  } = useScraping();

  const [scrapingPeriodDays, setScrapingPeriodDays] = useState<number | null>(null);
  const [tfaCodes, setTfaCodes] = useState<Record<string, string>>({});

  const { data: accounts, isLoading } = useQuery({
    queryKey: ["credentials-accounts", isDemoMode],
    queryFn: () => credentialsApi.getAccounts().then((res) => res.data),
  });

  const { data: providers } = useQuery({
    queryKey: ["providers", isDemoMode],
    queryFn: () => credentialsApi.getProviders().then((res) => res.data),
  });

  const fetchFieldsMutation = useMutation({
    mutationFn: (provider: string) => credentialsApi.getFields(provider),
    onSuccess: (res) => {
      setFormFields(res.data.fields);
      setStep(3);
    },
  });

  const resetForm = () => {
    setIsAddOpen(false);
    setStep(1);
    setSelectedService("");
    setSelectedProvider("");
    setAccountName("");
    setFields({});
    setFormFields([]);
    setEditingAccount(null);
    setIsViewOnly(false);
    setShowPasswords({});
  };

  const createMutation = useMutation({
    mutationFn: () =>
      credentialsApi.create({
        service: selectedService,
        provider: selectedProvider,
        account_name: accountName,
        credentials: fields,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credentials-accounts"] });
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (acc: CredentialAccount) =>
      credentialsApi.delete(acc.service, acc.provider, acc.account_name),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: ["credentials-accounts"] }),
  });

  // Bank Balances
  const { data: bankBalances } = useQuery({
    queryKey: ["bank-balances", isDemoMode],
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: lastScrapes } = useQuery({
    queryKey: ["last-scrapes", isDemoMode],
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
  });

  const setBalanceMutation = useMutation({
    mutationFn: bankBalancesApi.setBalance,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
      setEditingBalance(null);
      setBalanceInput("");
    },
    onError: (error: unknown) => {
      const axiosErr = error as { response?: { data?: { detail?: string } } };
      alert(axiosErr.response?.data?.detail || "Failed to set balance.");
    },
  });

  const [editingBalance, setEditingBalance] = useState<string | null>(null);
  const [balanceInput, setBalanceInput] = useState("");

  const getAccountBalance = (
    provider: string,
    accountName: string,
  ): BankBalance | undefined => {
    return bankBalances?.find(
      (b) => b.provider === provider && b.account_name === accountName,
    );
  };

  const isScrapedToday = (
    provider: string,
    accountName: string,
  ): boolean => {
    const scrape = lastScrapes?.find(
      (s) => s.provider === provider && s.account_name === accountName,
    );
    if (!scrape?.last_scrape_date) return false;
    const scrapeDate = new Date(scrape.last_scrape_date);
    const today = new Date();
    return (
      scrapeDate.getFullYear() === today.getFullYear() &&
      scrapeDate.getMonth() === today.getMonth() &&
      scrapeDate.getDate() === today.getDate()
    );
  };


  useEffect(() => {
    if (!isAddOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") resetForm();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isAddOpen]);

  const handleView = async (acc: CredentialAccount) => {
    setIsViewOnly(true);
    setEditingAccount(acc);
    setSelectedService(acc.service as "banks" | "credit_cards" | "insurances");
    setSelectedProvider(acc.provider);
    setAccountName(acc.account_name);

    try {
      const details = await credentialsApi.getAccountDetails(
        acc.service,
        acc.provider,
        acc.account_name,
      );
      const rawFields = details.data;
      const fieldNames = Object.keys(rawFields);
      setFormFields(fieldNames);
      setFields(rawFields);
      setStep(3);
      setIsAddOpen(true);
    } catch (err) {
      console.error("Failed to fetch details", err);
    }
  };

  const handleEdit = async (acc: CredentialAccount) => {
    setEditingAccount(acc);
    setSelectedService(acc.service as "banks" | "credit_cards" | "insurances");
    setSelectedProvider(acc.provider);
    setAccountName(acc.account_name);

    try {
      const details = await credentialsApi.getAccountDetails(
        acc.service,
        acc.provider,
        acc.account_name,
      );
      setFields(details.data);
      const fieldsMeta = await credentialsApi.getFields(acc.provider);
      setFormFields(fieldsMeta.data.fields);
      setStep(3);
      setIsAddOpen(true);
    } catch (err) {
      console.error("Failed to fetch details", err);
    }
  };

  const togglePasswordVisibility = (field: string) => {
    setShowPasswords((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  if (isLoading)
    return (
      <div className="space-y-4 md:space-y-8 p-4 md:p-8">
        <Skeleton variant="text" lines={2} className="w-64" />
        <div className="grid grid-cols-1 gap-4">
          <Skeleton variant="card" className="h-28" />
          <Skeleton variant="card" className="h-28" />
        </div>
      </div>
    );

  return (
    <div className="space-y-4 md:space-y-8 animate-in fade-in duration-500">
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between gap-3 md:gap-0">
        <div>
          <h1 className="text-2xl md:text-3xl font-bold">{t("dataSources.title")}</h1>
          <p className="text-[var(--text-muted)] mt-1">
            {t("dataSources.subtitle")}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 md:gap-3">
          <div className="relative">
            <select
              value={scrapingPeriodDays ?? "auto"}
              onChange={(e) =>
                setScrapingPeriodDays(e.target.value === "auto" ? null : Number(e.target.value))
              }
              disabled={isAnyScraping}
              className="appearance-none bg-[var(--surface)] border border-[var(--surface-light)] rounded-xl px-3 pe-7 py-2.5 text-xs font-bold text-white outline-none focus:border-[var(--primary)]/50 transition-colors disabled:opacity-50 cursor-pointer"
            >
              {SCRAPING_PERIODS.map((p) => (
                <option key={p.key} value={p.days ?? "auto"}>{t(`dataSources.scrapePeriod.${p.key}`)}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute end-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)] pointer-events-none" />
          </div>
          <button
            onClick={() => accounts && scrapeAll(accounts, scrapingPeriodDays)}
            disabled={isAnyScraping || !accounts?.length}
            className="flex items-center gap-2 px-5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] text-white rounded-xl font-bold hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            <RefreshCw size={16} className={isAnyScraping ? "animate-spin" : ""} />
            {isAnyScraping ? t("dataSources.scraping") : t("dataSources.scrapeAll")}
          </button>
          <button
            onClick={() => setIsAddOpen(true)}
            className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20"
          >
            <Plus size={18} /> {t("dataSources.connectAccount")}
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {accounts?.length === 0 ? (
          <div className="bg-[var(--surface)] rounded-2xl border border-dashed border-[var(--surface-light)] p-6 md:p-12 text-center">
            <div className="mx-auto w-16 h-16 bg-[var(--surface-light)] rounded-2xl flex items-center justify-center text-[var(--text-muted)] mb-4">
              <Globe size={32} />
            </div>
            <h3 className="text-xl font-bold mb-2">{t("dataSources.noAccountsConnected")}</h3>
            <p className="text-[var(--text-muted)] mb-8 max-w-sm mx-auto">
              {t("dataSources.noAccountsDesc")}
            </p>
            <button
              onClick={() => setIsAddOpen(true)}
              className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--surface-light)] text-white rounded-xl font-bold hover:bg-[var(--surface-base)] transition-all border border-white/5"
            >
              <Plus size={18} /> {t("dataSources.addFirstAccount")}
            </button>
          </div>
        ) : (
          (() => {
            const bankAccounts = accounts?.filter((a: CredentialAccount) => a.service === "banks") ?? [];
            const creditCardAccounts = accounts?.filter((a: CredentialAccount) => a.service === "credit_cards") ?? [];
            const insuranceAccounts = accounts?.filter((a: CredentialAccount) => a.service === "insurances") ?? [];

            const renderAccountCard = (acc: CredentialAccount, idx: number) => {
              const scraper = getScraperForAccount(acc);
              const isActive = scraper && (scraper.status === "in_progress" || scraper.status === "waiting_for_2fa");
              const lastScrape = lastScrapes?.find(
                (s: { service: string; provider: string; account_name: string }) => s.service === acc.service && s.provider === acc.provider && s.account_name === acc.account_name,
              );
              const tfaKey = `${acc.service}_${acc.provider}_${acc.account_name}`;

              return (
              <div
                key={`${acc.service}-${acc.provider}-${acc.account_name}-${idx}`}
                className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-3 md:p-5 hover:border-[var(--primary)]/30 hover:shadow-xl transition-all"
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 md:gap-0">
                <div className="flex items-center gap-3 md:gap-5">
                  <div
                    className={`p-3.5 rounded-2xl ${acc.service === "banks" ? "bg-blue-500/10 text-blue-400" : "bg-purple-500/10 text-purple-400"}`}
                  >
                    {acc.service === "banks" ? (
                      <Landmark size={24} />
                    ) : (
                      <CreditCard size={24} />
                    )}
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
                  {acc.service === "banks" &&
                    (() => {
                      const bal = getAccountBalance(
                        acc.provider,
                        acc.account_name,
                      );
                      const key = `${acc.provider}|${acc.account_name}`;
                      const isEditing = editingBalance === key;
                      const canSetBalance = isScrapedToday(
                        acc.provider,
                        acc.account_name,
                      );

                      if (isEditing) {
                        return (
                          <div className="flex items-center gap-2">
                            <input
                              type="number"
                              value={balanceInput}
                              onChange={(e) => setBalanceInput(e.target.value)}
                              placeholder="Enter balance..."
                              className="w-36 px-3 py-1.5 rounded-lg bg-[var(--bg)] border border-[var(--surface-light)] text-white text-sm focus:outline-none focus:border-[var(--primary)]"
                              autoFocus
                              onKeyDown={(e) => {
                                if (e.key === "Enter" && balanceInput) {
                                  setBalanceMutation.mutate({
                                    provider: acc.provider,
                                    account_name: acc.account_name,
                                    balance: parseFloat(balanceInput),
                                  });
                                }
                                if (e.key === "Escape") {
                                  setEditingBalance(null);
                                  setBalanceInput("");
                                }
                              }}
                            />
                            <button
                              onClick={() => {
                                if (balanceInput) {
                                  setBalanceMutation.mutate({
                                    provider: acc.provider,
                                    account_name: acc.account_name,
                                    balance: parseFloat(balanceInput),
                                  });
                                }
                              }}
                              className="p-1.5 rounded-lg bg-emerald-500/20 text-emerald-400 hover:bg-emerald-500/30 transition-all"
                            >
                              <Check size={16} />
                            </button>
                            <button
                              onClick={() => {
                                setEditingBalance(null);
                                setBalanceInput("");
                              }}
                              className="p-1.5 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-all"
                            >
                              <X size={16} />
                            </button>
                          </div>
                        );
                      }

                      return (
                        <div className="flex items-center gap-2">
                          {bal ? (
                            <span className="text-sm font-semibold text-amber-400">
                              {formatCurrency(bal.balance)}
                            </span>
                          ) : (
                            <span className="text-xs text-[var(--text-muted)] italic">
                              {t("dataSources.noBalanceSet")}
                            </span>
                          )}
                          <button
                            onClick={() => {
                              if (canSetBalance) {
                                setEditingBalance(key);
                                setBalanceInput(
                                  bal ? String(bal.balance) : "",
                                );
                              }
                            }}
                            disabled={!canSetBalance}
                            className={`p-1.5 rounded-lg transition-all ${
                              canSetBalance
                                ? "bg-amber-500/10 text-amber-400 hover:bg-amber-500/20"
                                : "bg-[var(--surface-light)] text-[var(--text-muted)] cursor-not-allowed opacity-50"
                            }`}
                            title={
                              canSetBalance
                                ? t("dataSources.setBalance")
                                : t("dataSources.scrapeFirstToSetBalance")
                            }
                          >
                            <DollarSign size={16} />
                          </button>
                        </div>
                      );
                    })()}
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
                        {scraper.error_message && (
                          <div className="relative group/err">
                            <Info size={12} className="text-red-400 cursor-help" />
                            <div className="absolute bottom-full end-0 mb-1 hidden group-hover/err:block z-50">
                              <div className="bg-gray-900 text-white text-[10px] p-2 rounded shadow-lg max-w-[200px] whitespace-normal border border-gray-700">
                                {scraper.error_message}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    )}
                    {(!scraper || !["in_progress", "waiting_for_2fa", "success", "failed"].includes(scraper.status)) && (
                      <>
                        {!lastScrape?.last_scrape_date ? (
                          <span className="text-[10px] text-[var(--text-muted)] italic">{t("dataSources.neverSynced")}</span>
                        ) : isScrapedToday(acc.provider, acc.account_name) ? (
                          <div className="flex items-center gap-1 px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30">
                            <CheckCircle2 size={12} className="text-emerald-400" />
                            <span className="text-[10px] font-semibold text-emerald-400">{t("dataSources.synced")}</span>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1 text-[var(--text-muted)]">
                            <Clock size={12} />
                            <span className="text-[10px]">{formatRelativeDate(lastScrape.last_scrape_date)}</span>
                          </div>
                        )}
                      </>
                    )}
                  </div>

                  <div className="flex gap-2">
                    {/* Scrape / Abort Button */}
                    {isActive ? (
                      <button
                        onClick={() => abortScraper(scraper!)}
                        className="p-2.5 rounded-xl bg-red-500/10 text-red-400 hover:bg-red-500/20 hover:text-red-300 transition-all"
                        title={t("dataSources.abortScraping")}
                      >
                        <XCircle size={20} />
                      </button>
                    ) : (
                      <button
                        onClick={() => startScraper(acc, scrapingPeriodDays)}
                        disabled={isAnyScraping}
                        className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                        title={t("dataSources.scrapeThisSource")}
                      >
                        <PlayCircle size={20} />
                      </button>
                    )}
                    <button
                      onClick={() => handleView(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
                      title={t("dataSources.viewDetails")}
                    >
                      <Eye size={20} />
                    </button>
                    <button
                      onClick={() => handleEdit(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all"
                      title={t("dataSources.editAccount")}
                    >
                      <Edit2 size={20} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(t("dataSources.confirmDisconnect", { name: acc.account_name })))
                          deleteMutation.mutate(acc);
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
                {scraper?.status === "waiting_for_2fa" && (
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
                          placeholder="Code"
                          maxLength={10}
                          className="w-28 bg-black/40 border border-amber-500/30 rounded-lg px-3 py-1.5 text-sm font-mono text-center outline-none focus:border-amber-400 text-white"
                          value={tfaCodes[tfaKey] || ""}
                          onChange={(e) =>
                            setTfaCodes((prev) => ({
                              ...prev,
                              [tfaKey]: e.target.value,
                            }))
                          }
                          onKeyDown={(e) => {
                            if (e.key === "Enter") {
                              const code = tfaCodes[tfaKey];
                              if (code) {
                                submitTfa(scraper, code);
                                setTfaCodes((prev) => ({
                                  ...prev,
                                  [tfaKey]: "",
                                }));
                              }
                            }
                          }}
                        />
                        <button
                          onClick={() => {
                            const code = tfaCodes[tfaKey];
                            if (code) {
                              submitTfa(scraper, code);
                              setTfaCodes((prev) => ({
                                ...prev,
                                [tfaKey]: "",
                              }));
                            }
                          }}
                          disabled={!tfaCodes[tfaKey] || tfaIsPending}
                          className="px-3 py-1.5 rounded-lg bg-amber-500 text-black text-xs font-bold hover:bg-amber-400 transition-all disabled:opacity-50"
                        >
                          {t("dataSources.verify")}
                        </button>
                        <button
                          onClick={() => resendTfa(scraper, scrapingPeriodDays)}
                          disabled={tfaIsPending}
                          className="px-3 py-1.5 rounded-lg bg-white/10 text-white text-xs font-bold hover:bg-white/20 transition-all disabled:opacity-50"
                        >
                          {t("dataSources.resend")}
                        </button>
                      </div>
                    </div>
                  </div>
                )}
              </div>
              );
            };

            return (
              <div className="space-y-4">
                {bankAccounts.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mb-2">
                      {t("dataSources.bankAccounts")}
                    </h3>
                    {bankAccounts.map((acc: CredentialAccount, idx: number) => renderAccountCard(acc, idx))}
                  </>
                )}
                {creditCardAccounts.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-6 mb-2">
                      {t("dataSources.creditCards")}
                    </h3>
                    {creditCardAccounts.map((acc: CredentialAccount, idx: number) => renderAccountCard(acc, idx))}
                  </>
                )}
                {insuranceAccounts.length > 0 && (
                  <>
                    <h3 className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide px-2 mt-6 mb-2">
                      {t("dataSources.insurance")}
                    </h3>
                    {insuranceAccounts.map((acc: CredentialAccount, idx: number) => renderAccountCard(acc, idx))}
                  </>
                )}
              </div>
            );
          })()
        )}
      </div>

      {/* Connection Modal */}
      {isAddOpen && (
        <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-3xl p-4 md:p-8 shadow-2xl w-full max-w-xl animate-in zoom-in-95 duration-200 relative overflow-hidden">
            <button
              onClick={resetForm}
              className="absolute top-6 end-6 p-2 rounded-xl hover:bg-[var(--surface-light)] text-[var(--text-muted)] transition-colors"
            >
              <X size={20} />
            </button>

            <div className="mb-4 md:mb-8">
              <h2 className="text-xl md:text-2xl font-black mb-2">
                {isViewOnly
                  ? t("dataSources.accountDetails")
                  : editingAccount
                    ? t("dataSources.editConnection")
                    : t("dataSources.connectNewAccount")}
              </h2>
              <div className="flex gap-2">
                <div
                  className={`h-1.5 flex-1 rounded-full transition-all ${step >= 1 ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"}`}
                />
                <div
                  className={`h-1.5 flex-1 rounded-full transition-all ${step >= 2 ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"}`}
                />
                <div
                  className={`h-1.5 flex-1 rounded-full transition-all ${step >= 3 ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"}`}
                />
              </div>
            </div>

            {step === 1 && (
              <div className="space-y-4 animate-in slide-in-from-right-4 duration-300">
                <p className="text-[var(--text-muted)] font-medium mb-6">
                  {t("dataSources.chooseServiceType")}
                </p>
                <button
                  onClick={() => {
                    setSelectedService("banks");
                    setStep(2);
                  }}
                  className="w-full flex items-center justify-between p-4 md:p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 group-hover:scale-110 transition-transform">
                      <Landmark size={24} />
                    </div>
                    <div className="text-start">
                      <p className="font-bold text-lg text-white">
                        {t("dataSources.bankAccount")}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {t("dataSources.bankAccountDesc")}
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="text-[var(--text-muted)]" />
                </button>
                <button
                  onClick={() => {
                    setSelectedService("credit_cards");
                    setStep(2);
                  }}
                  className="w-full flex items-center justify-between p-4 md:p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 group-hover:scale-110 transition-transform">
                      <CreditCard size={24} />
                    </div>
                    <div className="text-start">
                      <p className="font-bold text-lg text-white">
                        {t("dataSources.creditCard")}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {t("dataSources.creditCardDesc")}
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="text-[var(--text-muted)]" />
                </button>
                <button
                  onClick={() => {
                    setSelectedService("insurances");
                    setStep(2);
                  }}
                  className="w-full flex items-center justify-between p-4 md:p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-400 group-hover:scale-110 transition-transform">
                      <Shield size={24} />
                    </div>
                    <div className="text-start">
                      <p className="font-bold text-lg text-white">
                        {t("dataSources.insurance")}
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        {t("dataSources.insuranceDesc")}
                      </p>
                    </div>
                  </div>
                  <ChevronRight className="text-[var(--text-muted)]" />
                </button>
              </div>
            )}

            {step === 2 && (
              <div className="space-y-4 animate-in slide-in-from-right-4 duration-300">
                <p className="text-[var(--text-muted)] font-medium mb-6">
                  {t("dataSources.selectProvider")}
                </p>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pe-2">
                  {providers &&
                    providers[selectedService]?.map((p: string) => (
                      <button
                        key={p}
                        onClick={() => {
                          setSelectedProvider(p);
                          fetchFieldsMutation.mutate(p);
                        }}
                        className="p-4 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all font-bold text-center text-sm"
                      >
                        {humanizeProvider(p)}
                      </button>
                    ))}
                </div>
                <button
                  onClick={() => setStep(1)}
                  className="w-full py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
                >
                  {t("common.back")}
                </button>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-4 md:space-y-6 animate-in slide-in-from-right-4 duration-300">
                <p className="text-[var(--text-muted)] font-medium">
                  {isViewOnly ? t("dataSources.currentDetailsFor") : t("dataSources.enterDetailsFor")}{" "}
                  <span className="text-white font-black">
                    {humanizeProvider(selectedProvider)}
                  </span>
                  :
                </p>

                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      {t("dataSources.displayName")}
                    </label>
                    <input
                      type="text"
                      disabled={isViewOnly || !!editingAccount}
                      placeholder="e.g. My Investment Account"
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50"
                      value={accountName}
                      onChange={(e) => setAccountName(e.target.value)}
                    />
                  </div>

                  {formFields.map((field) => {
                    const isSensitive =
                      field.toLowerCase().includes("password") ||
                      field.toLowerCase().includes("secret");
                    return (
                      <div key={field} className="relative group/field">
                        <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                          {field.replace(/([A-Z])/g, " $1")}
                        </label>
                        <div className="relative">
                          <input
                            type={
                              isSensitive && !showPasswords[field]
                                ? "password"
                                : "text"
                            }
                            disabled={isViewOnly}
                            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50 pe-12"
                            value={fields[field] || ""}
                            onChange={(e) =>
                              setFields({ ...fields, [field]: e.target.value })
                            }
                          />
                          {isSensitive && (
                            <button
                              type="button"
                              onClick={() => togglePasswordVisibility(field)}
                              className="absolute end-4 top-1/2 -translate-y-1/2 p-2 text-[var(--text-muted)] hover:text-white transition-colors"
                              title={showPasswords[field] ? i18n.t("common.hide") : i18n.t("common.show")}
                            >
                              {showPasswords[field] ? (
                                <EyeOff size={16} />
                              ) : (
                                <Eye size={16} />
                              )}
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>

                {!isViewOnly && (
                  <div className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/10 flex gap-3">
                    <AlertCircle className="text-blue-400 shrink-0" size={20} />
                    <p className="text-xs text-blue-400/80 leading-relaxed font-medium">
                      {t("dataSources.credentialsSecurityNote")}
                    </p>
                  </div>
                )}

                <div className="flex gap-3">
                  {!isViewOnly && !editingAccount && (
                    <button
                      onClick={() => setStep(2)}
                      className="flex-1 py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
                    >
                      {t("common.back")}
                    </button>
                  )}
                  <button
                    onClick={
                      isViewOnly ? resetForm : () => createMutation.mutate()
                    }
                    disabled={
                      (!isViewOnly && !accountName) || createMutation.isPending
                    }
                    className="flex-[2] py-4 bg-[var(--primary)] rounded-2xl text-white font-black hover:bg-[var(--primary-dark)] transition-all shadow-xl shadow-[var(--primary)]/20 disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isViewOnly
                      ? t("common.close")
                      : createMutation.isPending
                        ? t("dataSources.saving")
                        : editingAccount
                          ? t("dataSources.saveChanges")
                          : t("dataSources.finishSetup")}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
