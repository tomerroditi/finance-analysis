import {
  createContext,
  useContext,
  useState,
  useEffect,
  useRef,
  type ReactNode,
} from "react";
import { testingApi } from "../services/api";
import { useQueryClient } from "@tanstack/react-query";
import {
  DEMO_MODE_STORAGE_KEY,
  readStoredDemoMode,
} from "../services/demoMode";

// Re-exported so existing imports of these two names from this module keep
// resolving. The canonical definitions live in `services/demoMode.ts` — a
// standalone module was needed because this file imports `testingApi` from
// `services/api.ts`, and `api.ts` in turn needs to read the stored flag on
// every request; putting both here would create a circular import.
// eslint-disable-next-line react-refresh/only-export-components
export { DEMO_MODE_STORAGE_KEY, readStoredDemoMode };

interface DemoModeContextType {
  isDemoMode: boolean;
  toggleDemoMode: (enabled: boolean) => Promise<void>;
  isLoading: boolean;
}

const DemoModeContext = createContext<DemoModeContextType | undefined>(
  undefined,
);

interface DemoModeProviderProps {
  children: ReactNode;
  /**
   * Pre-resolved demo flag, overriding localStorage. Exists for the unit-test
   * harness (`test-utils.tsx`), which renders components synchronously.
   */
  initialDemoMode?: boolean;
}

export function DemoModeProvider({
  children,
  initialDemoMode,
}: DemoModeProviderProps) {
  // Read synchronously: every key from `useQueryKeys()` carries this flag as
  // its last segment, so it must be correct BEFORE the first fetch. The old
  // implementation fetched it and blocked rendering until the round trip
  // finished; localStorage makes the gate unnecessary.
  const [isDemoMode, setIsDemoMode] = useState(
    initialDemoMode ?? readStoredDemoMode(),
  );
  const queryClient = useQueryClient();
  // Tracks the current flag for the status-check effect below, which only
  // runs once on mount ([queryClient] deps) — a closed-over `isDemoMode`
  // would go stale if the user toggles Demo Mode before the response
  // arrives. Synced after every render (never mutated during render itself,
  // which the react-hooks lint rule forbids).
  const isDemoModeRef = useRef(isDemoMode);
  useEffect(() => {
    isDemoModeRef.current = isDemoMode;
  });

  useEffect(() => {
    // The only reason to ask the server: a deployment (the shared Vercel
    // instance) may pin the mode and refuse the client's choice. A
    // non-forced answer is ignored — the client owns its own mode.
    testingApi
      .getDemoModeStatus()
      .then((res) => {
        if (!res.data.forced) return;
        // Side effects live outside the updater on purpose: React
        // double-invokes functional `setState` updaters under StrictMode
        // in dev, which would otherwise fire `resetQueries()` twice.
        if (isDemoModeRef.current !== res.data.demo_mode) {
          setIsDemoMode(res.data.demo_mode);
          void queryClient.resetQueries();
        }
      })
      .catch((err) => {
        console.error("Failed to fetch demo mode status:", err);
      });
  }, [queryClient]);

  const toggleDemoMode = async (enabled: boolean) => {
    if (enabled) {
      // Build the demo database if this is the first client to ask for it.
      // Idempotent by design: another client may be browsing demo data, and
      // rebuilding would wipe its session mid-browse.
      await testingApi.prepareDemo();
    }
    try {
      localStorage.setItem(DEMO_MODE_STORAGE_KEY, enabled ? "1" : "0");
    } catch {
      // A client that cannot persist the flag still switches for this
      // session; it just reverts to real mode on reload.
    }
    setIsDemoMode(enabled);
    await queryClient.resetQueries();
  };

  return (
    <DemoModeContext.Provider
      value={{ isDemoMode, toggleDemoMode, isLoading: false }}
    >
      {children}
    </DemoModeContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useDemoMode() {
  const context = useContext(DemoModeContext);
  if (context === undefined) {
    throw new Error("useDemoMode must be used within a DemoModeProvider");
  }
  return context;
}
