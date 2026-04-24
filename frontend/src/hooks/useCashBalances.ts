import { useQuery } from "@tanstack/react-query";
import { cashBalancesApi } from "../services/api";

/**
 * Shared hook for fetching cash balance envelopes.
 * Replaces 5 duplicate useQuery calls across modals and pages.
 */
export function useCashBalances(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["cash-balances"],
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
    enabled: options?.enabled,
  });
}
