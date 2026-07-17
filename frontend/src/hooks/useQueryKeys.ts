import { useMemo } from "react";
import { useDemoMode } from "../context/DemoModeContext";
import { makeQueryKeys } from "../services/queryKeys";

/**
 * Query-key factory bound to the current demo-mode flag.
 *
 * All server-data queries must build their keys through this hook so demo
 * and real data never share a cache entry and identical data always does.
 */
export function useQueryKeys() {
  const { isDemoMode } = useDemoMode();
  return useMemo(() => makeQueryKeys(isDemoMode), [isDemoMode]);
}
