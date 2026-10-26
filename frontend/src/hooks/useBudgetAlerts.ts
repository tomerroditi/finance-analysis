import { useQuery } from "@tanstack/react-query";
import { budgetApi, type BudgetAlertsResponse } from "../services/api";
import { useBudgetAlertSettings } from "./useBudgetAlertSettings";
import { useQueryKeys } from "./useQueryKeys";

/**
 * Fetch the current month's budget alerts (rules at >= the user's threshold).
 * Used by the sidebar bell badge and the alerts popup. Respects the user's
 * budget-alert settings: the query is disabled (and returns no data) when
 * alerts are turned off, and the configured threshold is sent to the backend.
 *
 * Asked as an explicit month, under the same key the budget Overview uses
 * for its month's alerts, so the two share one entry whenever the user's
 * threshold matches the Overview's.
 */
export function useBudgetAlerts() {
  const { enabled, threshold } = useBudgetAlertSettings();
  const qk = useQueryKeys();
  const today = new Date();
  const year = today.getFullYear();
  const month = today.getMonth() + 1;
  return useQuery<BudgetAlertsResponse>({
    queryKey: qk.budget.alertsMonth(year, month, threshold),
    queryFn: () => budgetApi.getMonthAlerts(year, month, threshold).then((res) => res.data),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}
