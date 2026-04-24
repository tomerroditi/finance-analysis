import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";
import { Liabilities } from "./Liabilities";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("Liabilities", () => {
  describe("rendering", () => {
    it("renders the page title", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText("Liabilities")).toBeInTheDocument();
      });
    });

    it("renders the subtitle", async () => {
      renderWithProviders(<Liabilities />);
      await waitFor(() => {
        expect(screen.getByText(/Track your loans and debts/i)).toBeInTheDocument();
      });
    });
  });

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
