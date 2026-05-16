import { useState } from "react";
import { useTranslation } from "react-i18next";
import { FileUp } from "lucide-react";

import { ImportAccountWizard } from "./ImportAccountWizard";

/**
 * Top-level "Import from File" button + creation wizard.
 */
export function ImportFileButton() {
  const { t } = useTranslation();
  const [isOpen, setIsOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="flex items-center gap-2 px-5 py-2.5 bg-[var(--surface)] border border-[var(--surface-light)] text-white rounded-xl font-bold hover:border-[var(--primary)]/50 hover:bg-[var(--primary)]/5 transition-all"
      >
        <FileUp size={16} />
        {t("dataSources.import.buttonLabel")}
      </button>
      {isOpen && (
        <ImportAccountWizard
          mode="create"
          isOpen={isOpen}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  );
}
