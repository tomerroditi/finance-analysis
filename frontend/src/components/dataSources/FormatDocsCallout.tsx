import { useTranslation } from "react-i18next";
import { Info, Download } from "lucide-react";

import { importedAccountsApi } from "../../services/api";

/**
 * Inline help block above the upload dropzone. Lists what columns the
 * importer expects and links to a downloadable template CSV.
 */
export function FormatDocsCallout() {
  const { t } = useTranslation();
  return (
    <div className="p-4 rounded-2xl bg-blue-500/5 border border-blue-500/15 space-y-2">
      <div className="flex items-center gap-2 text-blue-400">
        <Info size={16} />
        <span className="text-xs font-bold uppercase tracking-widest">
          {t("dataSources.import.docsTitle")}
        </span>
      </div>
      <ul className="text-xs text-blue-400/85 space-y-1 list-disc list-inside">
        <li>{t("dataSources.import.docsRequired")}</li>
        <li>{t("dataSources.import.docsOptional")}</li>
        <li>{t("dataSources.import.docsTypes")}</li>
        <li>{t("dataSources.import.docsSign")}</li>
        <li>{t("dataSources.import.docsBanner")}</li>
      </ul>
      <a
        href={importedAccountsApi.templateUrl()}
        download
        className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-300 hover:text-blue-200 underline"
      >
        <Download size={14} />
        {t("dataSources.import.docsTemplate")}
      </a>
    </div>
  );
}
