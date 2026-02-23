import { describe, it, expect, beforeEach } from "vitest";
import { useAppStore } from "./appStore";

describe("appStore", () => {
  beforeEach(() => {
    // Reset store to initial state between tests
    useAppStore.setState({
      sidebarOpen: true,
      selectedYear: new Date().getFullYear(),
      selectedMonth: new Date().getMonth() + 1,
      selectedService: "all",
      searchOpen: false,
      autoTaggingPanelOpen: true,
    });
  });

  describe("sidebar", () => {
    it("starts open", () => {
      expect(useAppStore.getState().sidebarOpen).toBe(true);
    });

    it("toggles closed then open", () => {
      useAppStore.getState().toggleSidebar();
      expect(useAppStore.getState().sidebarOpen).toBe(false);

      useAppStore.getState().toggleSidebar();
      expect(useAppStore.getState().sidebarOpen).toBe(true);
    });
  });

  describe("year/month selection", () => {
    it("defaults to current year and month", () => {
      const now = new Date();
      expect(useAppStore.getState().selectedYear).toBe(now.getFullYear());
      expect(useAppStore.getState().selectedMonth).toBe(now.getMonth() + 1);
    });

    it("sets year", () => {
      useAppStore.getState().setSelectedYear(2025);
      expect(useAppStore.getState().selectedYear).toBe(2025);
    });

    it("sets month", () => {
      useAppStore.getState().setSelectedMonth(6);
      expect(useAppStore.getState().selectedMonth).toBe(6);
    });
  });

  describe("service filter", () => {
    it("defaults to all", () => {
      expect(useAppStore.getState().selectedService).toBe("all");
    });

    it("sets service filter", () => {
      useAppStore.getState().setSelectedService("credit_cards");
      expect(useAppStore.getState().selectedService).toBe("credit_cards");
    });
  });

  describe("search", () => {
    it("starts closed", () => {
      expect(useAppStore.getState().searchOpen).toBe(false);
    });

    it("sets search open state", () => {
      useAppStore.getState().setSearchOpen(true);
      expect(useAppStore.getState().searchOpen).toBe(true);
    });
  });

  describe("auto tagging panel", () => {
    it("starts open", () => {
      expect(useAppStore.getState().autoTaggingPanelOpen).toBe(true);
    });

    it("toggles", () => {
      useAppStore.getState().toggleAutoTaggingPanel();
      expect(useAppStore.getState().autoTaggingPanelOpen).toBe(false);
    });
  });
});
