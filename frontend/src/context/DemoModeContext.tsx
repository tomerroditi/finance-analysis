import {
  createContext,
  useContext,
  useState,
  useEffect,
  type ReactNode,
} from "react";
import { testingApi } from "../services/api";
import { useQueryClient } from "@tanstack/react-query";

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
   * Pre-resolved demo flag. When supplied, children render immediately and
   * the initial-status gate is skipped (the status request still runs and
   * corrects the value if the backend disagrees).
   *
   * This exists for the unit-test harness (`test-utils.tsx`), which renders
   * components synchronously and would otherwise have to await the status
   * round-trip in every test. The app itself never passes it — `App.tsx`
   * mounts the gated provider, which is the whole point of the gate.
   */
  initialDemoMode?: boolean;
}

export function DemoModeProvider({
  children,
  initialDemoMode,
}: DemoModeProviderProps) {
  const [isDemoMode, setIsDemoMode] = useState(initialDemoMode ?? false);
  const [isResolved, setIsResolved] = useState(initialDemoMode !== undefined);
  const queryClient = useQueryClient();

  useEffect(() => {
    // Fetch initial status
    testingApi
      .getDemoModeStatus()
      .then((res) => {
        setIsDemoMode(res.data.demo_mode);
      })
      .catch((err) => {
        console.error("Failed to fetch demo mode status:", err);
      })
      .finally(() => {
        setIsResolved(true);
      });
  }, []);

  const toggleDemoMode = async (enabled: boolean) => {
    try {
      const res = await testingApi.toggleDemoMode(enabled);
      setIsDemoMode(res.data.demo_mode);
      // Reset all queries to clear cache and force refetch
      // This prevents stale data from the other mode from being shown
      await queryClient.resetQueries();
    } catch (err) {
      console.error("Failed to toggle demo mode:", err);
      throw err;
    }
  };

  // Nothing below this provider may render until the real flag is known.
  //
  // Every key from `useQueryKeys()` carries the demo flag as its last
  // segment. Rendering children while the flag is still at its `false`
  // placeholder made the whole app fetch once under `[..., false]` and then
  // refetch everything under `[..., true]` when the status resolved — and,
  // worse, the *demo* response for that first pass was cached (and
  // persisted to IndexedDB, since it passes `shouldDehydrateQuery`) under
  // the REAL-mode key, where it could later hydrate as the user's own data
  // with demo mode off. Gating on resolution makes the flag correct before
  // the first fetch, so that mix-up is structurally impossible.
  if (!isResolved) return null;

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
