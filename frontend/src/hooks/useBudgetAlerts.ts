import { useQuery } from "@tanstack/react-query";
import { budgetApi, type BudgetAlertsResponse } from "../services/api";
import { useBudgetAlertSettings } from "./useBudgetAlertSettings";

/**
 * Fetch the current month's budget alerts (rules at >= the user's threshold).
 * Used by the sidebar bell badge and the alerts popup. Respects the user's
 * budget-alert settings: the query is disabled (and returns no data) when
 * alerts are turned off, and the configured threshold is sent to the backend.
 */
export function useBudgetAlerts() {
  const { enabled, threshold } = useBudgetAlertSettings();
  return useQuery<BudgetAlertsResponse>({
    queryKey: ["budgetAlerts", "current", threshold],
    queryFn: () => budgetApi.getCurrentAlerts(threshold).then((res) => res.data),
    staleTime: 5 * 60 * 1000,
    enabled,
  });
}
