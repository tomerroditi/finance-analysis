import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Landmark, CreditCard, DollarSign, ChevronRight } from "lucide-react";

import { Modal } from "../common/Modal";
import { importedAccountsApi } from "../../services/api";
import { useNotify } from "../../context/DialogContext";
import type {
  ColumnMapping,
  ImportService,
  ImportedAccount,
} from "../../types/importedAccount";
import { FormatDocsCallout } from "./FormatDocsCallout";
import { UploadFileDropzone } from "./UploadFileDropzone";
import { ColumnMappingWizard } from "./ColumnMappingWizard";

interface CreateProps {
  mode: "create";
  isOpen: boolean;
  onClose: () => void;
}

interface EditProps {
  mode: "edit-mapping";
  isOpen: boolean;
  onClose: () => void;
  account: ImportedAccount;
}

type Props = CreateProps | EditProps;

/**
 * 3-step modal: service → metadata → upload + map.
 *
 * For mode="edit-mapping", steps 1–2 are skipped and the upload step
 * leads to a mapping wizard pre-filled with the saved mapping. Saving
 * updates `mapping_json` only; no import is run.
 */
export function ImportAccountWizard(props: Props) {
  const { t } = useTranslation();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const isEdit = props.mode === "edit-mapping";

  const [step, setStep] = useState<1 | 2 | 3>(isEdit ? 3 : 1);
  const [service, setService] = useState<ImportService | "">(
    isEdit ? props.account.service : "",
  );
  const [provider, setProvider] = useState(isEdit ? props.account.provider : "");
  const [accountName, setAccountName] = useState(
    isEdit ? props.account.account_name : "",
  );
  const [file, setFile] = useState<File | null>(null);

  const createMutation = useMutation({
    mutationFn: async (mapping: ColumnMapping) => {
      const created = await importedAccountsApi.create({
        service,
        provider,
        account_name: accountName,
        mapping,
      });
      const summary = await importedAccountsApi.upload(
        created.data.id,
        file as File,
      );
      return { created: created.data, summary: summary.data };
    },
    onSuccess: ({ summary }) => {
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] });
      notify.success(
        t("dataSources.import.importSummary", {
          inserted: summary.inserted,
          duplicates: summary.skipped_duplicates,
          invalid: summary.dropped_invalid,
        }),
      );
      reset();
      props.onClose();
    },
    onError: () => notify.error(t("dataSources.import.importFailed")),
  });

  const updateMappingMutation = useMutation({
    mutationFn: (mapping: ColumnMapping) => {
      if (!isEdit) throw new Error("not in edit mode");
      return importedAccountsApi.updateMapping(props.account.id, mapping);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["imported-accounts"] });
      notify.success(t("dataSources.import.createSuccess"));
      reset();
      props.onClose();
    },
    onError: () => notify.error(t("dataSources.import.importFailed")),
  });

  function reset() {
    setStep(isEdit ? 3 : 1);
    if (!isEdit) {
      setService("");
      setProvider("");
      setAccountName("");
    }
    setFile(null);
  }

  return (
    <Modal
      isOpen={props.isOpen}
      onClose={props.onClose}
      title={t(isEdit ? "dataSources.import.editTitle" : "dataSources.import.wizardTitle")}
      maxWidth="2xl"
    >
      <div className="p-4 md:p-6 space-y-4 overflow-y-auto">
        {!isEdit && (
          <div className="flex gap-2 mb-2">
            {[1, 2, 3].map((s) => (
              <div
                key={s}
                className={`h-1.5 flex-1 rounded-full transition-all ${
                  step >= s ? "bg-[var(--primary)]" : "bg-[var(--surface-light)]"
                }`}
              />
            ))}
          </div>
        )}

        {step === 1 && (
          <div className="space-y-3">
            <p className="text-[var(--text-muted)] text-sm">
              {t("dataSources.import.stepServiceLabel")}
            </p>
            <ServicePickRow
              icon={<Landmark size={22} />}
              label={t("dataSources.bankAccount")}
              onClick={() => {
                setService("banks");
                setStep(2);
              }}
            />
            <ServicePickRow
              icon={<CreditCard size={22} />}
              label={t("dataSources.creditCard")}
              onClick={() => {
                setService("credit_cards");
                setStep(2);
              }}
            />
            <ServicePickRow
              icon={<DollarSign size={22} />}
              label={t("dataSources.cash")}
              onClick={() => {
                setService("cash");
                setStep(2);
              }}
            />
          </div>
        )}

        {step === 2 && (
          <div className="space-y-3">
            <p className="text-[var(--text-muted)] text-sm">
              {t("dataSources.import.stepMetaLabel")}
            </p>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
                {t("dataSources.import.providerLabel")}
              </label>
              <input
                type="text"
                value={provider}
                onChange={(e) => setProvider(e.target.value)}
                placeholder={t("dataSources.import.providerPlaceholder")}
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-sm outline-none focus:border-[var(--primary)]"
              />
            </div>
            <div>
              <label className="block text-[10px] font-black uppercase tracking-widest text-[var(--text-muted)] mb-1.5">
                {t("dataSources.import.accountNameLabel")}
              </label>
              <input
                type="text"
                value={accountName}
                onChange={(e) => setAccountName(e.target.value)}
                placeholder={t("dataSources.import.accountNamePlaceholder")}
                className="w-full bg-[var(--surface-base)] border border-[var(--surface-light)] rounded-xl px-4 py-3 text-sm outline-none focus:border-[var(--primary)]"
              />
            </div>
            <div className="flex justify-end gap-3 pt-2">
              <button
                type="button"
                onClick={() => setStep(1)}
                className="px-4 py-2 text-sm text-[var(--text-muted)] hover:text-white"
              >
                {t("common.back")}
              </button>
              <button
                type="button"
                disabled={!provider.trim() || !accountName.trim()}
                onClick={() => setStep(3)}
                className="px-5 py-2.5 bg-[var(--primary)] text-white rounded-xl font-bold disabled:opacity-50"
              >
                {t("common.next")}
              </button>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="space-y-4">
            {!isEdit && <FormatDocsCallout />}
            {!file ? (
              <UploadFileDropzone onFile={setFile} />
            ) : (
              <ColumnMappingWizard
                file={file}
                initialMapping={isEdit ? props.account.mapping : null}
                saveLabelKey={
                  isEdit
                    ? "dataSources.import.mappingSaveOnlyButton"
                    : "dataSources.import.mappingSaveButton"
                }
                onSave={(mapping) => {
                  if (isEdit) {
                    updateMappingMutation.mutate(mapping);
                  } else {
                    createMutation.mutate(mapping);
                  }
                }}
              />
            )}
          </div>
        )}
      </div>
    </Modal>
  );
}

function ServicePickRow({
  icon,
  label,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="w-full flex items-center justify-between p-4 rounded-2xl bg-[var(--surface-base)] border border-[var(--surface-light)] hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all"
    >
      <div className="flex items-center gap-3">
        <div className="p-2.5 rounded-xl bg-[var(--surface-light)] text-[var(--text-muted)]">
          {icon}
        </div>
        <span className="font-bold text-base text-white">{label}</span>
      </div>
      <ChevronRight className="text-[var(--text-muted)]" />
    </button>
  );
}
