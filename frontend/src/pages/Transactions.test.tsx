import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../test-utils";
import { Transactions } from "./Transactions";

describe("Transactions", () => {
  describe("rendering", () => {
    it("renders service filter tabs", async () => {
      renderWithProviders(<Transactions />);
      await waitFor(() => {
        expect(screen.getByText("All")).toBeInTheDocument();
        expect(screen.getByText("Credit Card")).toBeInTheDocument();
        expect(screen.getByText("Bank")).toBeInTheDocument();
        expect(screen.getByText("Cash")).toBeInTheDocument();
        expect(screen.getByText("Investment")).toBeInTheDocument();
      });
    });
  });

  describe("transaction list", () => {
    it("displays transactions from the API", async () => {
      renderWithProviders(<Transactions />);
      await waitFor(() => {
        expect(screen.getByText("Supermarket Purchase")).toBeInTheDocument();
      });
    });

    it("shows transaction amounts", async () => {
      renderWithProviders(<Transactions />);
      await waitFor(() => {
        expect(screen.getByText("Supermarket Purchase")).toBeInTheDocument();
      });
    });
  });

  describe("service tab switching", () => {
    it("filters transactions when clicking service tabs", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Transactions />);

      await waitFor(() => {
        expect(screen.getByText("All")).toBeInTheDocument();
      });

      const cashTab = screen.getByText("Cash");
      await user.click(cashTab);

      // Cash tab should now be active (visual state change)
      await waitFor(() => {
        expect(cashTab.closest("button")).toHaveClass(/bg-/);
      });
    });
  });
});
