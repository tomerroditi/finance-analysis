import { useQuery } from "@tanstack/react-query";
import { updatesApi, type UpdateInfo } from "../services/api";

const SIX_HOURS_MS = 6 * 60 * 60 * 1000;

/**
 * Shared hook for the GitHub-Releases-backed update check.
 *
 * The backend caches the probe to disk for 24h, so polling here every 6h
 * costs at most one HTTP round-trip per session. Disabled in dev so a
 * Vite-served bundle doesn't pester the developer with "1.15.1 →
 * <whatever-was-released-this-week>" toasts.
 */
export function useUpdateCheck() {
  return useQuery<UpdateInfo>({
    queryKey: ["updateCheck"],
    queryFn: () => updatesApi.check().then((res) => res.data),
    staleTime: SIX_HOURS_MS,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    enabled: !import.meta.env.DEV,
    retry: false,
  });
}
