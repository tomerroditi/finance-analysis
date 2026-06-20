import { useQuery } from "@tanstack/react-query";
import { analyticsApi } from "../../services/api";
import { SankeyChart } from "../SankeyChart";
import { Skeleton } from "../common/Skeleton";
import { useDemoMode } from "../../context/DemoModeContext";
import { useTranslation } from "react-i18next";

/** Cash Flow (Sankey) dashboard card. */
export function CashFlowCard() {
  const { t } = useTranslation();
  const { isDemoMode } = useDemoMode();

  const { data: sankeyData, isLoading: sankeyLoading } = useQuery({
    queryKey: ["sankey", isDemoMode],
    queryFn: async () => (await analyticsApi.getSankeyData()).data,
  });

  return (
    <div className="bg-[var(--surface)] rounded-2xl border border-[var(--surface-light)] overflow-hidden flex flex-col">
      <div className="px-3 md:px-6 pt-4 md:pt-5">
        <h2 className="text-sm md:text-base font-bold">{t("dashboard.cashFlow")}</h2>
      </div>
      <div className="px-3 md:px-6 pb-4 md:pb-6 pt-4 min-h-[400px] md:h-[600px] overflow-y-auto flex flex-col">
        <div className="flex flex-col flex-1 min-h-0">
          {sankeyLoading ? (
            <Skeleton variant="chart" className="flex-1" />
          ) : (
            <div className="flex-1 min-h-0">
              <SankeyChart data={sankeyData} height={560} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
