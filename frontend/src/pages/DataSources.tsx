import { useState, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useScrollLock } from "../hooks/useScrollLock";
import {
  Plus,
  Globe,
  Landmark,
  CreditCard,
  ChevronLeft,
  ChevronRight,
  X,
  AlertCircle,
  Eye,
  EyeOff,
  RefreshCw,
  ChevronDown,
  Shield,
} from "lucide-react";
import {
  credentialsApi,
  bankBalancesApi,
  scrapingApi,
} from "../services/api";
import type { BankBalance, CredentialAccount } from "../services/api";

import { useScraping } from "../hooks/useScraping";
import { ProviderLogo } from "../components/common/ProviderLogo";
import { Skeleton } from "../components/common/Skeleton";
import { UpdateBankBalanceModal } from "../components/modals/UpdateBankBalanceModal";
import { AccountCard } from "../components/dataSources/AccountCard";
import { humanizeProvider } from "../utils/textFormatting";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { qkPrefix } from "../services/queryKeys";

// Sentinel the backend returns in place of stored secrets; sending it back
// on save keeps the stored value (see backend CredentialsService.MASK_SENTINEL).
const MASKED_VALUE = "__unchanged__";

const SCRAPING_PERIODS = [
  { key: "auto", days: null },
  { key: "weeks2", days: 14 },
  { key: "month1", days: 30 },
  { key: "months2", days: 60 },
  { key: "months3", days: 90 },
  { key: "months6", days: 180 },
  { key: "months12", days: 365 },
] as const;

export function DataSources() {
  const { t, i18n: i18nInstance } = useTranslation();
  const isRtl = i18nInstance.language === "he";
  const qk = useQueryKeys();
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
    resendCooldownRemaining, resendErrors,
  } = useScraping();

  const [scrapingPeriodDays, setScrapingPeriodDays] = useState<number | null>(null);
  const [tfaCodes, setTfaCodes] = useState<Record<string, string>>({});

  const { data: accounts, isLoading } = useQuery({
    queryKey: qk.credentials.accounts(),
    queryFn: () => credentialsApi.getAccounts().then((res) => res.data),
  });

  const { data: providers } = useQuery({
    queryKey: qk.credentials.providers(),
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
      queryClient.invalidateQueries({ queryKey: qkPrefix.credentialsAccounts });
      resetForm();
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (acc: CredentialAccount) =>
      credentialsApi.delete(acc.service, acc.provider, acc.account_name),
    onSuccess: () =>
      queryClient.invalidateQueries({ queryKey: qkPrefix.credentialsAccounts }),
  });

  // Bank Balances
  const { data: bankBalances } = useQuery({
    queryKey: qk.balances.bank(),
    queryFn: () => bankBalancesApi.getAll().then((res) => res.data),
  });

  const { data: lastScrapes } = useQuery({
    queryKey: qk.scraping.lastScrapes(),
    queryFn: () => scrapingApi.getLastScrapes().then((res) => res.data),
  });

  const [balanceModalAccount, setBalanceModalAccount] = useState<
    { provider: string; account_name: string; balance: number | null } | null
  >(null);

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
      <div className="flex flex-wrap items-center justify-end gap-2 md:gap-3">
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
              <Plus size={18} /> {t("dataSources.connectFirstAccount")}
            </button>
          </div>
        ) : (
          (() => {
            const bankAccounts = accounts?.filter((a: CredentialAccount) => a.service === "banks") ?? [];
            const creditCardAccounts = accounts?.filter((a: CredentialAccount) => a.service === "credit_cards") ?? [];
            const insuranceAccounts = accounts?.filter((a: CredentialAccount) => a.service === "insurances") ?? [];

            const renderAccountCard = (acc: CredentialAccount, idx: number) => {
              const scraper = getScraperForAccount(acc);
              const lastScrape = lastScrapes?.find(
                (s) => s.service === acc.service && s.provider === acc.provider && s.account_name === acc.account_name,
              );
              const tfaKey = `${acc.service}_${acc.provider}_${acc.account_name}`;
              const bal = getAccountBalance(acc.provider, acc.account_name);

              return (
                <AccountCard
                  key={`${acc.service}-${acc.provider}-${acc.account_name}-${idx}`}
                  acc={acc}
                  scraper={scraper}
                  lastScrapeDate={lastScrape?.last_scrape_date}
                  balance={bal}
                  scrapedToday={isScrapedToday(acc.provider, acc.account_name)}
                  isAnyScraping={isAnyScraping}
                  tfaIsPending={tfaIsPending}
                  tfaCode={tfaCodes[tfaKey] || ""}
                  onTfaCodeChange={(code) =>
                    setTfaCodes((prev) => ({ ...prev, [tfaKey]: code }))
                  }
                  onSubmitTfa={(code) => {
                    submitTfa(scraper!, code);
                    setTfaCodes((prev) => ({ ...prev, [tfaKey]: "" }));
                  }}
                  onResendTfa={() => resendTfa(scraper!)}
                  resendCooldownRemaining={
                    scraper ? resendCooldownRemaining(scraper.process_id) : 0
                  }
                  resendErrorInfo={
                    scraper ? resendErrors[scraper.process_id] : undefined
                  }
                  onStartScrape={(opts) =>
                    startScraper(acc, scrapingPeriodDays, opts)
                  }
                  onAbortScrape={() => abortScraper(scraper!)}
                  onOpenBalanceModal={() =>
                    setBalanceModalAccount({
                      provider: acc.provider,
                      account_name: acc.account_name,
                      balance: bal ? bal.balance : null,
                    })
                  }
                  onView={() => handleView(acc)}
                  onEdit={() => handleEdit(acc)}
                  onDelete={() => deleteMutation.mutate(acc)}
                />
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
              <div className={`space-y-4 animate-in duration-300 ${isRtl ? "slide-in-from-left-4" : "slide-in-from-right-4"}`}>
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
                  {isRtl ? <ChevronLeft className="text-[var(--text-muted)]" /> : <ChevronRight className="text-[var(--text-muted)]" />}
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
                  {isRtl ? <ChevronLeft className="text-[var(--text-muted)]" /> : <ChevronRight className="text-[var(--text-muted)]" />}
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
                  {isRtl ? <ChevronLeft className="text-[var(--text-muted)]" /> : <ChevronRight className="text-[var(--text-muted)]" />}
                </button>
              </div>
            )}

            {step === 2 && (
              <div className={`space-y-4 animate-in duration-300 ${isRtl ? "slide-in-from-left-4" : "slide-in-from-right-4"}`}>
                <p className="text-[var(--text-muted)] font-medium mb-6">
                  {t("dataSources.selectProvider")}
                </p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[340px] overflow-y-auto pe-2">
                  {providers &&
                    providers[selectedService]?.map((p: string) => (
                      <button
                        key={p}
                        onClick={() => {
                          setSelectedProvider(p);
                          fetchFieldsMutation.mutate(p);
                        }}
                        className="p-3 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all flex flex-col items-center gap-2"
                      >
                        <div className="w-12 h-12 rounded-xl bg-white flex items-center justify-center p-1.5 text-gray-700">
                          <ProviderLogo
                            provider={p}
                            service={selectedService}
                            size={36}
                            alt={humanizeProvider(p)}
                          />
                        </div>
                        <span className="font-bold text-xs text-center">
                          {humanizeProvider(p)}
                        </span>
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
              <div className={`space-y-4 md:space-y-6 animate-in duration-300 ${isRtl ? "slide-in-from-left-4" : "slide-in-from-right-4"}`}>
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
                      placeholder={t("dataSources.displayNamePlaceholder")}
                      className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50"
                      value={accountName}
                      onChange={(e) => setAccountName(e.target.value)}
                    />
                  </div>

                  {formFields.map((field) => {
                    const isSensitive =
                      field.toLowerCase().includes("password") ||
                      field.toLowerCase().includes("secret");
                    const isMasked = fields[field] === MASKED_VALUE;
                    return (
                      <div key={field} className="relative group/field">
                        <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                          {/* Known credential fields get a translated label;
                              unknown fields fall back to humanized camelCase. */}
                          {t(`dataSources.fields.${field}`, {
                            defaultValue: field.replace(/([A-Z])/g, " $1"),
                          })}
                        </label>
                        <div className="relative">
                          <input
                            type={
                              isSensitive && (isMasked || !showPasswords[field])
                                ? "password"
                                : "text"
                            }
                            disabled={isViewOnly}
                            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50 pe-12"
                            value={fields[field] || ""}
                            onFocus={(e) => {
                              if (isSensitive && isMasked) e.target.select();
                            }}
                            onChange={(e) =>
                              setFields({ ...fields, [field]: e.target.value })
                            }
                          />
                          {isSensitive && !isMasked && (
                            <button
                              type="button"
                              onClick={() => togglePasswordVisibility(field)}
                              className="absolute end-4 top-1/2 -translate-y-1/2 p-2 text-[var(--text-muted)] hover:text-white transition-colors"
                              title={showPasswords[field] ? t("common.hide") : t("common.show")}
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

      <UpdateBankBalanceModal
        isOpen={balanceModalAccount !== null}
        onClose={() => setBalanceModalAccount(null)}
        provider={balanceModalAccount?.provider ?? ""}
        accountName={balanceModalAccount?.account_name ?? ""}
        currentBalance={balanceModalAccount?.balance ?? null}
        isScrapedToday={
          balanceModalAccount
            ? isScrapedToday(balanceModalAccount.provider, balanceModalAccount.account_name)
            : false
        }
      />
    </div>
  );
}
