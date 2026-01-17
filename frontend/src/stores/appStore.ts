import { create } from "zustand";

interface AppState {
  // Sidebar state
  sidebarOpen: boolean;
  toggleSidebar: () => void;

  // Selected filters
  selectedYear: number;
  selectedMonth: number;
  setSelectedYear: (year: number) => void;
  setSelectedMonth: (month: number) => void;

  // Active service filter for transactions
  selectedService: "all" | "credit_cards" | "banks" | "cash";
  setSelectedService: (
    service: "all" | "credit_cards" | "banks" | "cash",
  ) => void;

  // Global Search
  searchOpen: boolean;
  setSearchOpen: (open: boolean) => void;
}

export const useAppStore = create<AppState>((set) => ({
  // Sidebar
  sidebarOpen: true,
  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  // Filters - default to current month/year
  selectedYear: new Date().getFullYear(),
  selectedMonth: new Date().getMonth() + 1,
  setSelectedYear: (year) => set({ selectedYear: year }),
  setSelectedMonth: (month) => set({ selectedMonth: month }),

  // Service filter
  selectedService: "all",
  setSelectedService: (service) => set({ selectedService: service }),

  // Global Search
  searchOpen: false,
  setSearchOpen: (open) => set({ searchOpen: open }),
}));
