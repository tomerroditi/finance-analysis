import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { Liabilities } from "./Liabilities";

describe("Liabilities", () => {
  describe("liability cards", () => {
    it("displays liability names from the API", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText("Home Mortgage")).toBeInTheDocument();
      });
    });

    it("shows lender information", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText(/Bank Hapoalim/i)).toBeInTheDocument();
      });
    });

    it("shows add liability button", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText(/Add Liability/i)).toBeInTheDocument();
      });
    });
  });

  describe("debt overview", () => {
    it("renders debt over time section", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText(/Debt Over Time/i)).toBeInTheDocument();
      });
    });
  });
});
