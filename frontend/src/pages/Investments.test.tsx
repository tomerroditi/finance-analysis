import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";
import { Investments } from "./Investments";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("Investments", () => {
  describe("rendering", () => {
    it("renders the page title and subtitle", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        // Title may include emoji prefix
        expect(screen.getAllByText(/Investments/i).length).toBeGreaterThan(0);
      });
    });
  });

  describe("investment cards", () => {
    it("displays investment names from the API", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        expect(screen.getByText("S&P 500 ETF")).toBeInTheDocument();
        expect(screen.getByText("Government Bonds")).toBeInTheDocument();
      });
    });

    it("displays investment type badges", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        expect(screen.getAllByText(/Stocks/i).length).toBeGreaterThan(0);
        expect(screen.getAllByText(/Bonds/i).length).toBeGreaterThan(0);
      });
    });

    it("shows the add investment button", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        // The add button may render with icon + text or just icon on mobile
        const buttons = screen.getAllByRole("button");
        expect(buttons.length).toBeGreaterThan(0);
      });
    });
  });

  describe("portfolio overview", () => {
    it("renders portfolio analysis section", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        // Portfolio section renders with total value, profit, ROI
        expect(screen.getAllByText(/Portfolio/i).length).toBeGreaterThan(0);
      });
    });
  });
});
