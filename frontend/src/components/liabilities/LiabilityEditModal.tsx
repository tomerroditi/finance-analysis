import { useTranslation } from "react-i18next";
import { Modal } from "../common/Modal";

export interface EditLiabilityForm {
  id: number | null;
  name: string;
  lender: string;
  interest_rate: string;
  notes: string;
}

interface Props {
  form: EditLiabilityForm;
  setForm: React.Dispatch<React.SetStateAction<EditLiabilityForm>>;
  onClose: () => void;
  isPending: boolean;
  onSubmit: () => void;
}

/** "Edit Liability" modal: name / lender / rate / notes. */
export function LiabilityEditModal({
  form,
  setForm,
  onClose,
  isPending,
  onSubmit,
}: Props) {
  const { t } = useTranslation();

  return (
    <Modal
      isOpen={form.id != null}
      onClose={onClose}
      title={t("liabilities.editLiability")}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 overflow-y-auto">
        <div className="space-y-4">
          <div>
            <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
              {t("liabilities.name")}
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
              {t("liabilities.interestRate")} (%)
            </label>
            <input
              type="number"
              step="0.01"
              className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
              value={form.interest_rate}
              onChange={(e) => setForm({ ...form, interest_rate: e.target.value })}
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
            disabled={!form.name || isPending}
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
