import { useTranslation } from "react-i18next";
import { AlertTriangle, CheckCircle, TrendingUp } from "lucide-react";
import { Modal } from "../common/Modal";
import { SelectDropdown } from "../common/SelectDropdown";
import { formatCurrency } from "../../utils/numberFormatting";
import { formatDate } from "../../utils/dateFormatting";
import type { CurrentRates } from "../../services/api";
import { AMORTIZATION_METHODS, LOAN_TYPES, isPrimeBased } from "./loanTypes";

export interface NewLiabilityForm {
  name: string;
  lender: string;
  tag: string;
  principal_amount: string;
  interest_rate: string;
  loan_type: string;
  amortization_method: string;
  rate_spread: string;
  rate_reset_months: string;
  term_months: string;
  start_date: string;
  notes: string;
}

export interface TagDetection {
  has_receipt: boolean;
  receipt: { date: string; amount: number } | null;
  payments: Array<{ date: string; amount: number }>;
}

interface Props {
  isOpen: boolean;
  onClose: () => void;
  form: NewLiabilityForm;
  setForm: React.Dispatch<React.SetStateAction<NewLiabilityForm>>;
  tagDetection: TagDetection | null;
  availableTags: string[];
  onTagChange: (tag: string) => Promise<void>;
  onCreateTag: (name: string) => Promise<void>;
  currentRates: CurrentRates | null;
  isPending: boolean;
  onSubmit: () => void;
}

/** "Add Liability" modal: tag-driven detection + manual fallback fields. */
export function LiabilityCreateModal({
  isOpen,
  onClose,
  form,
  setForm,
  tagDetection,
  availableTags,
  onTagChange,
  onCreateTag,
  currentRates,
  isPending,
  onSubmit,
}: Props) {
  const { t } = useTranslation();

  const primeBased = isPrimeBased(form.loan_type);
  const isVariable = form.loan_type === "variable_unlinked";
  const rateFieldsValid = primeBased
    ? !!form.rate_spread && (!isVariable || !!form.rate_reset_months)
    : !!form.interest_rate;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("liabilities.addLiability")}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 overflow-y-auto">
        <div className="space-y-4">
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.name")} *
            </label>
            <input
              type="text"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.lender")}
            </label>
            <input
              type="text"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
              value={form.lender}
              onChange={(e) => setForm({ ...form, lender: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.tag")} *
            </label>
            <SelectDropdown
              options={availableTags.map((tag: string) => ({ label: tag, value: tag }))}
              value={form.tag}
              onChange={onTagChange}
              placeholder={t("liabilities.selectTag")}
              onCreateNew={onCreateTag}
            />
            {tagDetection && !tagDetection.has_receipt && (
              <div className="flex items-start gap-2 mt-2 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-sm">
                <AlertTriangle size={16} className="text-amber-400 shrink-0 mt-0.5" />
                <span className="text-amber-300">
                  {t("liabilities.noReceiptWarning")}
                </span>
              </div>
            )}
            {tagDetection?.has_receipt && (
              <div className="flex items-start gap-2 mt-2 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-sm">
                <CheckCircle size={16} className="text-emerald-400 shrink-0 mt-0.5" />
                <span className="text-emerald-300">
                  {t("liabilities.receiptDetected", {
                    amount: formatCurrency(tagDetection.receipt?.amount ?? 0),
                    date: tagDetection.receipt ? formatDate(tagDetection.receipt.date) : "",
                    payments: tagDetection.payments.length,
                  })}
                </span>
              </div>
            )}
          </div>
          {tagDetection && !tagDetection.has_receipt && (
            <>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.principalAmount")} *
                </label>
                <input
                  type="number"
                  step="0.01"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={form.principal_amount}
                  onChange={(e) =>
                    setForm({ ...form, principal_amount: e.target.value })
                  }
                />
              </div>
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.startDate")} *
                </label>
                <input
                  type="date"
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={form.start_date}
                  onChange={(e) => setForm({ ...form, start_date: e.target.value })}
                />
              </div>
            </>
          )}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                {t("liabilities.loanType")} *
              </label>
              <SelectDropdown
                options={LOAN_TYPES.map((value) => ({
                  label: t(`liabilities.loanTypes.${value}`),
                  value,
                }))}
                value={form.loan_type}
                onChange={(loan_type: string) => setForm({ ...form, loan_type })}
              />
            </div>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                {t("liabilities.amortizationMethod")} *
              </label>
              <SelectDropdown
                options={AMORTIZATION_METHODS.map((value) => ({
                  label: t(`liabilities.amortizationMethods.${value}`),
                  value,
                }))}
                value={form.amortization_method}
                onChange={(amortization_method: string) =>
                  setForm({ ...form, amortization_method })
                }
              />
            </div>
          </div>
          {primeBased && !!currentRates?.prime && (
            <div className="flex items-start gap-2 p-3 bg-sky-500/10 border border-sky-500/30 rounded-xl text-sm">
              <TrendingUp size={16} className="text-sky-400 shrink-0 mt-0.5" />
              <span className="text-sky-300">
                {t("liabilities.currentPrimeHint", {
                  prime: currentRates.prime,
                  boi: currentRates.boi_rate,
                  date: currentRates.as_of ? formatDate(currentRates.as_of) : "",
                })}
              </span>
            </div>
          )}
          {!primeBased && (
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                {t("liabilities.interestRate")} (%) *
              </label>
              <input
                type="number"
                step="0.01"
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                value={form.interest_rate}
                onChange={(e) => setForm({ ...form, interest_rate: e.target.value })}
              />
            </div>
          )}
          {primeBased && (
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                  {t("liabilities.rateSpread")} (%) *
                </label>
                <input
                  type="number"
                  step="0.01"
                  placeholder={t("liabilities.spreadPlaceholder")}
                  className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                  value={form.rate_spread}
                  onChange={(e) => setForm({ ...form, rate_spread: e.target.value })}
                />
              </div>
              {isVariable && (
                <div>
                  <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
                    {t("liabilities.rateResetMonths")} *
                  </label>
                  <input
                    type="number"
                    min="1"
                    className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
                    value={form.rate_reset_months}
                    onChange={(e) =>
                      setForm({ ...form, rate_reset_months: e.target.value })
                    }
                  />
                </div>
              )}
            </div>
          )}
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.termMonths")} *
            </label>
            <input
              type="number"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
              value={form.term_months}
              onChange={(e) => setForm({ ...form, term_months: e.target.value })}
            />
          </div>
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.notes")}
            </label>
            <textarea
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium resize-none"
              rows={3}
              value={form.notes}
              onChange={(e) => setForm({ ...form, notes: e.target.value })}
            />
          </div>
        </div>
        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            disabled={
              !form.name ||
              !form.tag ||
              !tagDetection ||
              (!tagDetection.has_receipt &&
                (!form.principal_amount || !form.start_date)) ||
              !rateFieldsValid ||
              !form.term_months ||
              isPending
            }
            onClick={onSubmit}
            className="flex-1 py-3 text-sm font-bold bg-[var(--primary)] text-white rounded-xl hover:bg-[var(--primary-dark)] transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPending ? "..." : t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
