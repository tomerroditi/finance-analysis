import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  Shield,
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
} from "lucide-react";
import {
  credentialsApi,
  bankBalancesApi,
  scrapingApi,
} from "../services/api";
import type { BankBalance } from "../services/api";

import { useDemoMode } from "../context/TestModeContext";

export function DataSources() {
  const { isDemoMode } = useDemoMode();
  const queryClient = useQueryClient();
  const [isAddOpen, setIsAddOpen] = useState(false);
  const [step, setStep] = useState(1);
  const [selectedService, setSelectedService] = useState<
    "banks" | "credit_cards" | ""
  >("");
  const [selectedProvider, setSelectedProvider] = useState("");
  const [accountName, setAccountName] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [formFields, setFormFields] = useState<string[]>([]);
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>(
    {},
  );
  const [editingAccount, setEditingAccount] = useState<any>(null);
  const [isViewOnly, setIsViewOnly] = useState(false);

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
    mutationFn: (acc: any) =>
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
    onError: (error: any) => {
      alert(error.response?.data?.detail || "Failed to set balance.");
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

  const formatCurrency = (val: number) =>
    new Intl.NumberFormat("he-IL", {
      style: "currency",
      currency: "ILS",
    }).format(val);

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

  const handleView = async (acc: any) => {
    setIsViewOnly(true);
    setEditingAccount(acc);
    setSelectedService(acc.service);
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

  const handleEdit = async (acc: any) => {
    setEditingAccount(acc);
    setSelectedService(acc.service);
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
      <div className="p-8 text-center text-[var(--text-muted)]">Loading...</div>
    );

  return (
    <div className="space-y-8 animate-in fade-in duration-500">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Data Sources</h1>
          <p className="text-[var(--text-muted)] mt-1">
            Securely manage your connected financial institutions and
            credentials
          </p>
        </div>
        <button
          onClick={() => setIsAddOpen(true)}
          className="flex items-center gap-2 px-6 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold hover:bg-[var(--primary-dark)] transition-all shadow-lg shadow-[var(--primary)]/20"
        >
          <Plus size={18} /> Connect Account
        </button>
      </div>

      <div className="grid grid-cols-1 gap-4">
        {accounts?.length === 0 ? (
          <div className="bg-[var(--surface)] rounded-2xl border border-dashed border-[var(--surface-light)] p-12 text-center">
            <div className="mx-auto w-16 h-16 bg-[var(--surface-light)] rounded-2xl flex items-center justify-center text-[var(--text-muted)] mb-4">
              <Globe size={32} />
            </div>
            <h3 className="text-xl font-bold mb-2">No Accounts Connected</h3>
            <p className="text-[var(--text-muted)] mb-8 max-w-sm mx-auto">
              Connect your bank or credit card to automatically import
              transactions and track your finances in real-time.
            </p>
            <button
              onClick={() => setIsAddOpen(true)}
              className="inline-flex items-center gap-2 px-6 py-3 bg-[var(--surface-light)] text-white rounded-xl font-bold hover:bg-[var(--surface-base)] transition-all border border-white/5"
            >
              <Plus size={18} /> Add Your First Account
            </button>
          </div>
        ) : (
          <div className="space-y-4">
            {accounts?.map((acc: any, idx: number) => (
              <div
                key={idx}
                className="group bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] p-5 flex items-center justify-between hover:border-[var(--primary)]/30 hover:shadow-xl transition-all"
              >
                <div className="flex items-center gap-5">
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
                        {acc.provider}
                      </span>
                    </div>
                    <p className="text-sm text-[var(--text-muted)] font-medium capitalize">
                      {acc.service} Account
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-4">
                  <div className="hidden sm:flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/10 text-emerald-400 text-[10px] font-bold uppercase tracking-widest">
                    <Shield size={12} /> Secure Connection
                  </div>
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
                              No balance set
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
                                ? "Set Balance"
                                : "Scrape today first to set balance"
                            }
                          >
                            <DollarSign size={16} />
                          </button>
                        </div>
                      );
                    })()}
                  <div className="flex gap-2 opacity-0 group-hover:opacity-100 transition-all">
                    <button
                      onClick={() => handleView(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-white transition-all"
                      title="View Details"
                    >
                      <Eye size={20} />
                    </button>
                    <button
                      onClick={() => handleEdit(acc)}
                      className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)] hover:text-[var(--primary)] transition-all"
                      title="Edit Account"
                    >
                      <Edit2 size={20} />
                    </button>
                    <button
                      onClick={() => {
                        if (window.confirm(`Disconnect "${acc.account_name}"?`))
                          deleteMutation.mutate(acc);
                      }}
                      className="p-2.5 rounded-xl bg-red-500/10 text-red-500 hover:bg-red-500 hover:text-white transition-all"
                      title="Disconnect Account"
                    >
                      <Trash2 size={20} />
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Connection Modal */}
      {isAddOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-300">
          <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-3xl p-8 shadow-2xl w-full max-w-xl animate-in zoom-in-95 duration-200 relative overflow-hidden">
            <button
              onClick={resetForm}
              className="absolute top-6 right-6 p-2 rounded-xl hover:bg-[var(--surface-light)] text-[var(--text-muted)] transition-colors"
            >
              <X size={20} />
            </button>

            <div className="mb-8">
              <h2 className="text-2xl font-black mb-2">
                {isViewOnly
                  ? "Account Details"
                  : editingAccount
                    ? "Edit Connection"
                    : "Connect New Account"}
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
                  Choose the type of service you want to connect:
                </p>
                <button
                  onClick={() => {
                    setSelectedService("banks");
                    setStep(2);
                  }}
                  className="w-full flex items-center justify-between p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-blue-500/10 text-blue-400 group-hover:scale-110 transition-transform">
                      <Landmark size={24} />
                    </div>
                    <div className="text-left">
                      <p className="font-bold text-lg text-white">
                        Bank Account
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        Checkings, Investments, or Business accounts
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
                  className="w-full flex items-center justify-between p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
                >
                  <div className="flex items-center gap-4">
                    <div className="p-3 rounded-xl bg-purple-500/10 text-purple-400 group-hover:scale-110 transition-transform">
                      <CreditCard size={24} />
                    </div>
                    <div className="text-left">
                      <p className="font-bold text-lg text-white">
                        Credit Card
                      </p>
                      <p className="text-xs text-[var(--text-muted)]">
                        Personal or Corporate credit cards
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
                  Select your provider:
                </p>
                <div className="grid grid-cols-2 gap-3 max-h-[300px] overflow-y-auto pr-2">
                  {providers &&
                    providers[selectedService]?.map((p: string) => (
                      <button
                        key={p}
                        onClick={() => {
                          setSelectedProvider(p);
                          fetchFieldsMutation.mutate(p);
                        }}
                        className="p-4 rounded-xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all font-bold text-center text-sm capitalize"
                      >
                        {p}
                      </button>
                    ))}
                </div>
                <button
                  onClick={() => setStep(1)}
                  className="w-full py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
                >
                  Back
                </button>
              </div>
            )}

            {step === 3 && (
              <div className="space-y-6 animate-in slide-in-from-right-4 duration-300">
                <p className="text-[var(--text-muted)] font-medium">
                  {isViewOnly ? "Current" : "Enter"} details for{" "}
                  <span className="text-white font-black capitalize">
                    {selectedProvider}
                  </span>
                  :
                </p>

                <div className="space-y-4">
                  <div>
                    <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                      Display Name
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
                            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50 pr-12"
                            value={fields[field] || ""}
                            onChange={(e) =>
                              setFields({ ...fields, [field]: e.target.value })
                            }
                          />
                          {isSensitive && (
                            <button
                              type="button"
                              onClick={() => togglePasswordVisibility(field)}
                              className="absolute right-4 top-1/2 -translate-y-1/2 p-2 text-[var(--text-muted)] hover:text-white transition-colors"
                              title={showPasswords[field] ? "Hide" : "Show"}
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
                      Your credentials are encrypted and stored securely using
                      your system keyring. We never store raw passwords in our
                      database.
                    </p>
                  </div>
                )}

                <div className="flex gap-3">
                  {!isViewOnly && !editingAccount && (
                    <button
                      onClick={() => setStep(2)}
                      className="flex-1 py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
                    >
                      Back
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
                      ? "Close"
                      : createMutation.isPending
                        ? "Saving..."
                        : editingAccount
                          ? "Save Changes"
                          : "Finish Setup"}
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
