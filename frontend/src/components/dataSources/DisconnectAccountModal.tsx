import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Archive, Trash2 } from "lucide-react";
import { Modal } from "../common/Modal";

interface DisconnectAccountModalProps {
  isOpen: boolean;
  /** Display name of the account being disconnected (user data). */
  accountName: string;
  isPending?: boolean;
  onClose: () => void;
  /** `deleteData` mirrors the backend's `delete_data` query param. */
  onConfirm: (deleteData: boolean) => void;
}

/** Disconnect confirmation that forces an explicit keep-or-wipe choice for the
 * account's collected data. Keeping is the pre-selected, non-destructive
 * default — the wipe option is never selected on open. */
export function DisconnectAccountModal({
  isOpen,
  accountName,
  isPending = false,
  onClose,
  onConfirm,
}: DisconnectAccountModalProps) {
  const { t } = useTranslation();
  const groupName = useId();
  // Non-destructive default. The parent remounts this modal per target
  // account (keyed), so a fresh open always starts back on "keep".
  const [deleteData, setDeleteData] = useState(false);
  const warningRef = useRef<HTMLDivElement>(null);

  // On a short viewport the warning is revealed *below* the scroll container's
  // fold, so picking "delete everything" on a phone left the single most
  // important sentence in this dialog clipped in half with nothing prompting
  // the user to scroll. Pull it into view instead.
  useEffect(() => {
    if (!deleteData) return;
    warningRef.current?.scrollIntoView({ block: "nearest" });
  }, [deleteData]);

  const optionClasses = (selected: boolean, destructive: boolean) =>
    [
      "flex items-start gap-3 p-3 md:p-4 rounded-xl border cursor-pointer transition-all",
      selected
        ? destructive
          ? "border-[var(--danger)] bg-[var(--danger)]/10"
          : "border-[var(--primary)] bg-[var(--primary)]/5"
        : "border-[var(--surface-light)] bg-[var(--surface-base)] hover:border-[var(--primary)]/40",
    ].join(" ");

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={t("dataSources.disconnectAccount")}
      titleIcon={<AlertTriangle size={20} className="text-[var(--danger)]" />}
      maxWidth="lg"
    >
      <div className="p-4 md:p-6 space-y-4 overflow-y-auto">
        <p className="text-sm text-[var(--text)] leading-relaxed">
          {t("dataSources.disconnectIntro", { name: accountName })}
        </p>

        <fieldset className="space-y-3">
          <legend className="text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-2">
            {t("dataSources.dataChoiceLegend")}
          </legend>

          <label className={optionClasses(!deleteData, false)}>
            <input
              type="radio"
              name={groupName}
              checked={!deleteData}
              onChange={() => setDeleteData(false)}
              className="mt-1 h-4 w-4 shrink-0 accent-[var(--primary)]"
            />
            <span className="text-start">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <Archive size={14} className="text-[var(--primary)] shrink-0" />
                {t("dataSources.keepDataOption")}
              </span>
              <span className="block mt-1 text-xs text-[var(--text-muted)] leading-relaxed">
                {t("dataSources.keepDataDesc")}
              </span>
            </span>
          </label>

          <label className={optionClasses(deleteData, true)}>
            <input
              type="radio"
              name={groupName}
              checked={deleteData}
              onChange={() => setDeleteData(true)}
              className="mt-1 h-4 w-4 shrink-0 accent-[var(--danger)]"
            />
            <span className="text-start">
              <span className="flex items-center gap-2 text-sm font-bold text-white">
                <Trash2 size={14} className="text-[var(--danger)] shrink-0" />
                {t("dataSources.deleteDataOption")}
              </span>
              <span className="block mt-1 text-xs text-[var(--text-muted)] leading-relaxed">
                {t("dataSources.deleteDataDesc")}
              </span>
            </span>
          </label>
        </fieldset>

        {deleteData && (
          <div
            ref={warningRef}
            role="alert"
            className="flex gap-2 p-3 rounded-xl bg-[var(--danger)]/10 border border-[var(--danger)]/30"
          >
            <AlertTriangle size={16} className="text-[var(--danger)] shrink-0 mt-0.5" />
            <p className="text-xs font-semibold text-[var(--danger)] leading-relaxed">
              {t("dataSources.deleteDataWarning")}
            </p>
          </div>
        )}
      </div>

      <div className="px-4 md:px-6 py-4 flex flex-col-reverse sm:flex-row gap-3 border-t border-[var(--surface-light)] bg-[var(--surface-base)] shrink-0">
        <button
          onClick={onClose}
          disabled={isPending}
          className="flex-1 min-h-[44px] px-4 py-2.5 rounded-xl border border-[var(--surface-light)] hover:bg-[var(--surface-light)] text-sm font-semibold text-[var(--text)] transition-colors disabled:opacity-50"
        >
          {t("common.cancel")}
        </button>
        <button
          onClick={() => onConfirm(deleteData)}
          disabled={isPending}
          className={`flex-1 min-h-[44px] px-4 py-2.5 rounded-xl text-sm font-semibold text-white shadow-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed ${
            deleteData
              ? "bg-[var(--danger)] hover:brightness-110 shadow-red-500/20"
              : "bg-[var(--primary)] hover:bg-[var(--primary-dark)] shadow-[var(--primary)]/20"
          }`}
        >
          {deleteData
            ? t("dataSources.confirmDisconnectDelete")
            : t("dataSources.confirmDisconnectKeep")}
        </button>
      </div>
    </Modal>
  );
}
