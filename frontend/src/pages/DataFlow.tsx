import { useTranslation } from "react-i18next";
import { DataFlowDiagram } from "../components/dataflow/DataFlowDiagram";

export function DataFlow() {
  const { t } = useTranslation();

  return (
    <div className="flex flex-col h-[calc(100dvh-theme(spacing.14))] md:h-dvh -m-2 sm:-m-4 md:-m-8">
      <div className="px-4 md:px-8 py-3 border-b border-[var(--surface-light)]">
        <h1 className="text-lg md:text-xl font-bold">{t("dataFlow.title")}</h1>
        <p className="text-xs text-[var(--text-muted)]">{t("dataFlow.subtitle")}</p>
      </div>
      <DataFlowDiagram />
    </div>
  );
}
