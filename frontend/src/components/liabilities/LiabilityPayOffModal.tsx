import { useTranslation } from "react-i18next";
import { Modal } from "../common/Modal";

export interface PayOffForm {
  id: number | null;
  date: string;
}

interface Props {
  form: PayOffForm;
  setForm: React.Dispatch<React.SetStateAction<PayOffForm>>;
  onClose: () => void;
  isPending: boolean;
  onSubmit: () => void;
}

/** "Pay Off" modal: pick the paid-off date and confirm. */
export function LiabilityPayOffModal({
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
      title={t("liabilities.payOff")}
      maxWidth="sm"
    >
      <div className="p-4 md:p-6 overflow-y-auto">
        <div>
          <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
            {t("liabilities.paidOffDate")}
          </label>
          <input
            type="date"
            className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 outline-none focus:border-[var(--primary)] transition-all font-medium"
            value={form.date}
            onChange={(e) => setForm({ ...form, date: e.target.value })}
          />
        </div>
        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 py-3 text-sm font-bold text-[var(--text-muted)] hover:text-white transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            disabled={!form.date || isPending}
            onClick={onSubmit}
            className="flex-1 py-3 text-sm font-bold bg-emerald-600 text-white rounded-xl hover:bg-emerald-700 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isPending ? "..." : t("liabilities.payOff")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
