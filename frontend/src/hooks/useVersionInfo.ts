import { useQuery } from "@tanstack/react-query";
import { versionApi, type VersionInfo } from "../services/api";

/**
 * Shared hook for the running backend's version + platform identity.
 *
 * Used by the About panel ("you are on v1.15.1") and by the macOS-only
 * Uninstall section (visible only when ``platform === "darwin"``).
 * Cached for the lifetime of the page since the answer doesn't change.
 */
export function useVersionInfo() {
  return useQuery<VersionInfo>({
    queryKey: ["versionInfo"],
    queryFn: () => versionApi.get().then((res) => res.data),
    staleTime: Infinity,
    gcTime: Infinity,
  });
}
