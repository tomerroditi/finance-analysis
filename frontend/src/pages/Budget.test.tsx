import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test-utils";
import { Budget } from "./Budget";

describe("Budget", () => {
  describe("rendering", () => {
    it("renders both tab buttons", async () => {
      renderWithProviders(<Budget />);
      await waitFor(() => {
        expect(screen.getByText(/Monthly Budget/i)).toBeInTheDocument();
        expect(screen.getByText(/Project Budgets/i)).toBeInTheDocument();
      });
    });

    it("lands on the overview, not a single budget kind", async () => {
      renderWithProviders(<Budget />);
      await waitFor(() => {
        const overviewTab = screen.getByText(/^Overview$/i);
        expect(overviewTab.closest("button")).toHaveClass(/bg-/);
      });
      // The per-kind tabs are reachable but not selected — opening the page
      // should answer "how am I doing overall", not drop the user into one kind.
      expect(
        screen.getByText(/Monthly Budget/i).closest("button"),
      ).not.toHaveClass(/bg-\[var\(--surface\)\]/);
    });
  });

  describe("tab switching", () => {
    it("switches to project budgets view", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Budget />);

      await waitFor(() => {
        expect(screen.getByText(/Project Budgets/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/Project Budgets/i));

      await waitFor(() => {
        const projectTab = screen.getByText(/Project Budgets/i);
        expect(projectTab.closest("button")).toHaveClass(/bg-/);
      });
    });

    it("switches back to monthly budget view", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Budget />);

      await waitFor(() => {
        expect(screen.getByText(/Project Budgets/i)).toBeInTheDocument();
      });

      await user.click(screen.getByText(/Project Budgets/i));
      await user.click(screen.getByText(/Monthly Budget/i));

      await waitFor(() => {
        const monthlyTab = screen.getByText(/Monthly Budget/i);
        expect(monthlyTab.closest("button")).toHaveClass(/bg-/);
      });
    });
  });
});
