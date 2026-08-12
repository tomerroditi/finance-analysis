import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ChevronLeft,
  ChevronRight,
  CreditCard,
  Eye,
  EyeOff,
  Landmark,
  Shield,
  X,
} from "lucide-react";
import { credentialsApi } from "../../services/api";
import type { CredentialAccount } from "../../services/api";
import { ProviderLogo } from "../common/ProviderLogo";
import { useScrollLock } from "../../hooks/useScrollLock";
import { humanizeProvider } from "../../utils/textFormatting";
import { useQueryKeys } from "../../hooks/useQueryKeys";
import { qkPrefix } from "../../services/queryKeys";

/**
 * Sentinel the backend returns in place of stored secrets; sending it back on
 * save keeps the stored value (see backend `CredentialsService.MASK_SENTINEL`).
 */
const MASKED_VALUE = "__unchanged__";

type Service = "banks" | "credit_cards" | "insurances" | "";

export type ConnectModalMode = "create" | "edit" | "view";

interface ConnectAccountModalProps {
  mode: ConnectModalMode | null;
  /** The account being edited or viewed. Null in create mode. */
  account: CredentialAccount | null;
  onClose: () => void;
}

const SERVICE_CHOICES: Array<{
  service: Exclude<Service, "">;
  icon: typeof Landmark;
  iconClass: string;
  titleKey: string;
  descKey: string;
}> = [
  {
    service: "banks",
    icon: Landmark,
    iconClass: "bg-blue-500/10 text-blue-400",
    titleKey: "dataSources.bankAccount",
    descKey: "dataSources.bankAccountDesc",
  },
  {
    service: "credit_cards",
    icon: CreditCard,
    iconClass: "bg-purple-500/10 text-purple-400",
    titleKey: "dataSources.creditCard",
    descKey: "dataSources.creditCardDesc",
  },
  {
    service: "insurances",
    icon: Shield,
    iconClass: "bg-emerald-500/10 text-emerald-400",
    titleKey: "dataSources.insurance",
    descKey: "dataSources.insuranceDesc",
  },
];

/**
 * The connect / edit / view credential dialog for Data Sources.
 *
 * Owns its own wizard state (service → provider → fields) so the page is left
 * holding one `modal` value instead of ten pieces of form state. Rendering it
 * only while `mode` is set means every open starts from a clean form.
 *
 * The three modes differ in where the field list comes from, and that
 * difference is deliberate:
 * - **create** — the provider's declared field list (`GET /credentials/fields`).
 * - **edit** — stored values for prefill AND the provider's field list, so a
 *   field added since the account was created still shows up.
 * - **view** — the stored payload's own keys only, so the dialog shows exactly
 *   what is on record and nothing more (secrets arrive masked).
 */
export function ConnectAccountModal({
  mode,
  account,
  onClose,
}: ConnectAccountModalProps) {
  const { t, i18n: i18nInstance } = useTranslation();
  const isRtl = i18nInstance.language === "he";
  const qk = useQueryKeys();
  const queryClient = useQueryClient();

  const isViewOnly = mode === "view";
  const isEditing = mode === "edit" || mode === "view";

  // Seeded from props rather than synced in an effect: the page unmounts this
  // component on close (and keys it per target), so "initial" is the only
  // state these ever need. Edit/view also open straight on the details step —
  // the wizard's first two steps are meaningless for an existing account, and
  // routing through them flashed the service chooser before the fetch landed.
  const [step, setStep] = useState(() => (mode === "create" ? 1 : 3));
  const [selectedService, setSelectedService] = useState<Service>(
    () => (account?.service as Service) ?? "",
  );
  const [selectedProvider, setSelectedProvider] = useState(
    () => account?.provider ?? "",
  );
  const [accountName, setAccountName] = useState(() => account?.account_name ?? "");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [formFields, setFormFields] = useState<string[]>([]);
  const [showPasswords, setShowPasswords] = useState<Record<string, boolean>>({});

  useScrollLock(mode !== null);

  const { data: providers } = useQuery({
    queryKey: qk.credentials.providers(),
    queryFn: () => credentialsApi.getProviders().then((res) => res.data),
    enabled: mode === "create",
  });

  // Load the stored values for edit/view. Runs once per open because the page
  // unmounts this component on close.
  useEffect(() => {
    if (!account || mode === "create") return;
    let cancelled = false;
    (async () => {
      try {
        const details = await credentialsApi.getAccountDetails(
          account.service,
          account.provider,
          account.account_name,
        );
        if (cancelled) return;
        setFields(details.data);
        if (mode === "view") {
          // Exactly what's on record — no provider fields the user never filled.
          setFormFields(Object.keys(details.data));
        } else {
          const fieldsMeta = await credentialsApi.getFields(account.provider);
          if (cancelled) return;
          setFormFields(fieldsMeta.data.fields);
        }
      } catch (err) {
        console.error("Failed to fetch details", err);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [account, mode]);

  useEffect(() => {
    if (mode === null) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [mode, onClose]);

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
      queryClient.invalidateQueries({ queryKey: qkPrefix.credentialsAccounts });
      onClose();
    },
  });

  const togglePasswordVisibility = (field: string) => {
    setShowPasswords((prev) => ({ ...prev, [field]: !prev[field] }));
  };

  if (mode === null) return null;

  const slideIn = isRtl ? "slide-in-from-left-4" : "slide-in-from-right-4";

  return (
    <div className="modal-overlay fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-in fade-in duration-300">
      <div className="bg-[var(--surface)] border border-[var(--surface-light)] rounded-3xl p-4 md:p-8 shadow-2xl w-full max-w-[calc(100vw-2rem)] sm:max-w-xl animate-in zoom-in-95 duration-200 relative overflow-hidden">
        <button
          onClick={onClose}
          className="absolute top-6 end-6 p-2 rounded-xl hover:bg-[var(--surface-light)] text-[var(--text-muted)] transition-colors"
          aria-label={t("common.close")}
        >
          <X size={20} />
        </button>

        <div className="mb-4 md:mb-8">
          <h2 className="text-xl md:text-2xl font-black mb-2">
            {isViewOnly
              ? t("dataSources.accountDetails")
              : isEditing
                ? t("dataSources.editConnection")
                : t("dataSources.connectNewAccount")}
          </h2>
          <div className="flex gap-2">
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-1.5 flex-1 rounded-full transition-all ${
                  step >= s ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"
                }`}
              />
            ))}
          </div>
        </div>

        {step === 1 && (
          <div className={`space-y-4 animate-in duration-300 ${slideIn}`}>
            <p className="text-[var(--text-muted)] font-medium mb-6">
              {t("dataSources.chooseServiceType")}
            </p>
            {SERVICE_CHOICES.map(({ service, icon: Icon, iconClass, titleKey, descKey }) => (
              <button
                key={service}
                onClick={() => {
                  setSelectedService(service);
                  setStep(2);
                }}
                className="w-full flex items-center justify-between p-4 md:p-6 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all group"
              >
                <div className="flex items-center gap-4">
                  <div
                    className={`p-3 rounded-xl ${iconClass} group-hover:scale-110 transition-transform`}
                  >
                    <Icon size={24} />
                  </div>
                  <div className="text-start">
                    <p className="font-bold text-lg text-white">{t(titleKey)}</p>
                    <p className="text-xs text-[var(--text-muted)]">{t(descKey)}</p>
                  </div>
                </div>
                {isRtl ? (
                  <ChevronLeft className="text-[var(--text-muted)]" />
                ) : (
                  <ChevronRight className="text-[var(--text-muted)]" />
                )}
              </button>
            ))}
          </div>
        )}

        {step === 2 && (
          <div className={`space-y-4 animate-in duration-300 ${slideIn}`}>
            <p className="text-[var(--text-muted)] font-medium mb-6">
              {t("dataSources.selectProvider")}
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 max-h-[340px] overflow-y-auto pe-2">
              {providers?.[selectedService]?.map((p: string) => (
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
          <div className={`space-y-4 md:space-y-6 animate-in duration-300 ${slideIn}`}>
            <p className="text-[var(--text-muted)] font-medium">
              {isViewOnly
                ? t("dataSources.currentDetailsFor")
                : t("dataSources.enterDetailsFor")}{" "}
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
                  disabled={isEditing}
                  placeholder={t("dataSources.displayNamePlaceholder")}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3.5 outline-none focus:border-[var(--primary)] transition-all font-medium disabled:opacity-50"
                  value={accountName}
                  onChange={(e) => setAccountName(e.target.value)}
                />
              </div>

              {/* Edit/view open immediately and fill in when the stored values
                  land — placeholders keep the dialog from jumping in height. */}
              {isEditing && formFields.length === 0 && (
                <div className="space-y-4" aria-hidden="true">
                  <div className="h-[74px] rounded-xl bg-[var(--surface-base)] animate-pulse" />
                  <div className="h-[74px] rounded-xl bg-[var(--surface-base)] animate-pulse" />
                </div>
              )}

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
                          {showPasswords[field] ? <EyeOff size={16} /> : <Eye size={16} />}
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
              {!isEditing && (
                <button
                  onClick={() => setStep(2)}
                  className="flex-1 py-4 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
                >
                  {t("common.back")}
                </button>
              )}
              <button
                onClick={isViewOnly ? onClose : () => createMutation.mutate()}
                disabled={(!isViewOnly && !accountName) || createMutation.isPending}
                className="flex-[2] py-4 bg-[var(--primary)] rounded-2xl text-white font-black hover:bg-[var(--primary-dark)] transition-all shadow-xl shadow-[var(--primary)]/20 disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isViewOnly
                  ? t("common.close")
                  : createMutation.isPending
                    ? t("dataSources.saving")
                    : mode === "edit"
                      ? t("dataSources.saveChanges")
                      : t("dataSources.finishSetup")}
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
