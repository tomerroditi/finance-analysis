import { create } from "zustand";

interface AppState {
  // Sidebar state
  sidebarOpen: boolean;
  toggleSidebar: () => void;

  // Mobile sidebar overlay
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;

  // Selected filters
  selectedYear: number;
  selectedMonth: number;
  setSelectedYear: (year: number) => void;
  setSelectedMonth: (month: number) => void;

  // Active service filter for transactions
  selectedService: "all" | "credit_cards" | "banks" | "cash" | "manual_investments" | "refunds";
  setSelectedService: (
    service: "all" | "credit_cards" | "banks" | "cash" | "manual_investments" | "refunds",
  ) => void;

  // Auto Tagging Panel (Transactions page sidebar)
  autoTaggingPanelOpen: boolean;
  toggleAutoTaggingPanel: () => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Sidebar
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  // Mobile sidebar
  mobileSidebarOpen: false,
  setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),

  // Filters - default to current month/year
  selectedYear: new Date().getFullYear(),
  selectedMonth: new Date().getMonth() + 1,
  setSelectedYear: (year) => set({ selectedYear: year }),
  setSelectedMonth: (month) => set({ selectedMonth: month }),

  // Service filter
  selectedService: "all",
  setSelectedService: (service) => set({ selectedService: service }),

  // Auto Tagging Panel
  autoTaggingPanelOpen: false,
  toggleAutoTaggingPanel: () => set((state) => ({ autoTaggingPanelOpen: !state.autoTaggingPanelOpen })),
}));
