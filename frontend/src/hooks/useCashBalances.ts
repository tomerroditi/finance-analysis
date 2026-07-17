import { useQuery } from "@tanstack/react-query";
import { cashBalancesApi } from "../services/api";
import { useQueryKeys } from "./useQueryKeys";

/**
 * Shared hook for fetching cash balance envelopes.
 * Replaces 5 duplicate useQuery calls across modals and pages.
 */
export function useCashBalances(options?: { enabled?: boolean }) {
  const qk = useQueryKeys();
  return useQuery({
    queryKey: qk.balances.cash(),
    queryFn: () => cashBalancesApi.getAll().then((res) => res.data),
    enabled: options?.enabled,
  });
}
