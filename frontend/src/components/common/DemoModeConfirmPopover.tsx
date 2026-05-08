import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useDemoMode } from "../../context/DemoModeContext";

interface DemoModeConfirmPopoverProps {
  onClose: () => void;
}

export function DemoModeConfirmPopover({
  onClose,
}: DemoModeConfirmPopoverProps) {
  const { toggleDemoMode } = useDemoMode();
  const { t } = useTranslation();
  const [isPending, setIsPending] = useState(false);

  const handleConfirm = async () => {
    setIsPending(true);
    try {
      await toggleDemoMode(true);
      onClose();
    } finally {
      setIsPending(false);
    }
  };

  return (
    <div className="mt-2 p-4 bg-[var(--surface-light)] rounded-xl border border-[var(--surface-light)] text-sm text-center">
      <p className="text-[var(--text-muted)] mb-3">
        {t("emptyStates.demoConfirmDescription")}
      </p>
      <div className="flex items-center justify-center gap-3">
        <button
          type="button"
          onClick={handleConfirm}
          disabled={isPending}
          className="px-4 py-1.5 rounded-lg bg-[var(--primary)] text-white font-medium hover:bg-[var(--primary)]/90 transition-colors disabled:opacity-50"
        >
          {t("emptyStates.demoConfirmEnable")}
        </button>
        <button
          type="button"
          onClick={onClose}
          className="text-sm text-[var(--text-muted)] hover:text-[var(--text)] transition-colors"
        >
          {t("emptyStates.demoConfirmCancel")}
        </button>
      </div>
    </div>
  );
}
