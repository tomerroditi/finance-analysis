import { useMemo } from "react";
import { useTranslation } from "react-i18next";
import { buildLayers, buildPlatformFeatures, buildCallouts, connectionDefs } from "./dataFlowData";
import enContent from "./dataFlowContent.en";
import heContent from "./dataFlowContent.he";
import type { DataFlowContent } from "./dataFlowData";

const contentMap: Record<string, DataFlowContent> = {
  en: enContent,
  he: heContent,
};

export function useDataFlowData() {
  const { i18n } = useTranslation();
  const lang = i18n.language;

  return useMemo(() => {
    const content = contentMap[lang] ?? enContent;
    return {
      layers: buildLayers(content),
      details: content.details,
      platformFeatures: buildPlatformFeatures(content),
      callouts: buildCallouts(content),
      connectionDefs,
    };
  }, [lang]);
}
