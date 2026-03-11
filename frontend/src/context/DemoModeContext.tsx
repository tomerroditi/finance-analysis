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

export function DemoModeProvider({ children }: { children: ReactNode }) {
  const [isDemoMode, setIsDemoMode] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
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
        setIsLoading(false);
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

  return (
    <DemoModeContext.Provider value={{ isDemoMode, toggleDemoMode, isLoading }}>
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
