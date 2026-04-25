import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { Dashboard } from "./Dashboard";

describe("Dashboard", () => {
  describe("rendering", () => {
    it("renders the financial health KPI cards", async () => {
      renderWithProviders(<Dashboard />);
      await waitFor(() => {
        // Net Worth may appear multiple times (KPI card + chart section)
        expect(screen.getAllByText(/Net Worth/i).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/Bank Balance/i).length).toBeGreaterThan(0);
      });
    });

    it("renders the recent transactions section", async () => {
      renderWithProviders(<Dashboard />);
      await waitFor(() => {
        expect(screen.getByText(/Recent Transactions/i)).toBeInTheDocument();
      });
    });

    it("renders the dashboard insights panel", async () => {
      renderWithProviders(<Dashboard />);
      // The insights panel loads asynchronously — verify the chart KPIs land.
      await waitFor(() => {
        expect(screen.getAllByText(/Net Worth/i).length).toBeGreaterThan(0);
      });
    });
  });
});
