import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { DollarSign } from "lucide-react";
import { Modal } from "../common/Modal";
import { bankBalancesApi } from "../../services/api";
import { useNotify } from "../../context/DialogContext";
import { humanizeProvider } from "../../utils/textFormatting";
import { formatCurrency } from "../../utils/numberFormatting";

interface UpdateBankBalanceModalProps {
  isOpen: boolean;
  onClose: () => void;
  provider: string;
  accountName: string;
  currentBalance: number | null;
  isScrapedToday: boolean;
}

export function UpdateBankBalanceModal({
  isOpen,
  onClose,
  provider,
  accountName,
  currentBalance,
  isScrapedToday,
}: UpdateBankBalanceModalProps) {
  const { t } = useTranslation();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const [value, setValue] = useState("");

  // Re-seed the input whenever the modal (re)opens for a possibly different account.
  useEffect(() => {
    if (isOpen) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setValue(currentBalance != null ? String(currentBalance) : "");
    }
  }, [isOpen, currentBalance]);

  const mutation = useMutation({
    mutationFn: (data: Parameters<typeof bankBalancesApi.setBalance>[0]) =>
      bankBalancesApi.setBalance(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["bank-balances"] });
      queryClient.invalidateQueries({ queryKey: ["net-worth-over-time"] });
      onClose();
    },
    onError: (error: unknown) => {
      const axiosErr = error as { response?: { data?: { detail?: string } } };
      notify.error(axiosErr.response?.data?.detail || t("bankBalance.failed"));
    },
  });

  const canSave = isScrapedToday && value.trim() !== "" && !mutation.isPending;

  const submit = () => {
    if (!canSave) return;
    mutation.mutate({
      provider,
      account_name: accountName,
      balance: parseFloat(value),
    });
  };

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("bankBalance.title")}
      titleIcon={<DollarSign size={20} className="text-amber-400" />}
      maxWidth="md"
    >
      <div className="p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="text-[var(--text-muted)]">{humanizeProvider(provider)}</span>
          <span className="font-medium text-white truncate" dir="auto">{accountName}</span>
        </div>

        <p className="text-xs text-[var(--text-muted)] leading-relaxed">
          {t("bankBalance.explanation")}
        </p>

        {!isScrapedToday && (
          <p className="text-xs text-amber-400 bg-amber-500/10 rounded-lg px-3 py-2">
            {t("bankBalance.scrapeNote")}
          </p>
        )}

        <div className="space-y-1">
          <label htmlFor="bank-balance-input" className="text-xs text-[var(--text-muted)]">
            {t("bankBalance.balanceLabel")}
          </label>
          <input
            id="bank-balance-input"
            type="number"
            value={value}
            disabled={!isScrapedToday}
            onChange={(e) => setValue(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") submit();
            }}
            placeholder={t("bankBalance.placeholder")}
            autoFocus
            className="w-full px-3 py-2 rounded-lg bg-[var(--bg)] border border-[var(--surface-light)] text-white text-sm focus:outline-none focus:border-[var(--primary)] disabled:opacity-50 disabled:cursor-not-allowed"
          />
          {currentBalance != null && (
            <p className="text-[11px] text-[var(--text-muted)]">
              {t("bankBalance.current")}: {formatCurrency(currentBalance)}
            </p>
          )}
        </div>

        <div className="flex items-center justify-end gap-2 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded-lg text-sm text-[var(--text-muted)] hover:bg-[var(--surface-light)] transition-colors"
          >
            {t("common.cancel")}
          </button>
          <button
            onClick={submit}
            disabled={!canSave}
            className="px-4 py-2 rounded-lg text-sm font-medium bg-amber-500/90 text-black hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {t("common.save")}
          </button>
        </div>
      </div>
    </Modal>
  );
}
