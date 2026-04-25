import { useQuery } from "@tanstack/react-query";
import { budgetApi, type BudgetAlertsResponse } from "../services/api";

/**
 * Fetch the current month's budget alerts (rules at >=80% spend by default).
 * Used by the sidebar bell badge and the alerts popup.
 */
export function useBudgetAlerts() {
  return useQuery<BudgetAlertsResponse>({
    queryKey: ["budgetAlerts", "current"],
    queryFn: () => budgetApi.getCurrentAlerts().then((res) => res.data),
    staleTime: 5 * 60 * 1000,
  });
}
