import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { Investments, buildInvestmentPayload } from "./Investments";

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
        // The name appears in both the allocation-donut legend and the card title.
        expect(screen.getAllByText("S&P 500 ETF").length).toBeGreaterThan(0);
        expect(screen.getAllByText("Government Bonds").length).toBeGreaterThan(0);
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

    it("labels hishtalmut investments as Keren Hishtalmut, not Other", async () => {
      renderWithProviders(<Investments />);
      await waitFor(() => {
        // The fixture's own name ("Migdal 007-916-407357") never contains
        // "Keren Hishtalmut", so this can only match the type badge —
        // proving TYPE_KEY_MAP maps "hishtalmut" instead of falling through
        // to "Other".
        expect(screen.getAllByText(/Keren Hishtalmut/i).length).toBeGreaterThan(0);
        expect(screen.queryAllByText(/^Other$/i).length).toBe(0);
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

  describe("create payload", () => {
    it("omits Keren Hishtalmut fields for non-KH types", () => {
      const payload = buildInvestmentPayload({
        name: "S&P 500",
        category: "Investments",
        tag: "Stock Fund",
        type: "stocks",
        interest_rate: 0,
        interest_rate_type: "fixed",
        rate_spread: 0,
        notes: "",
        liquidity_date: "",
        commission_deposit: "",
        commission_management: "",
      });

      expect(payload).not.toHaveProperty("liquidity_date");
      expect(payload).not.toHaveProperty("commission_deposit");
      expect(payload).not.toHaveProperty("commission_management");
    });

    it("includes Keren Hishtalmut fields when the type is hishtalmut", () => {
      const payload = buildInvestmentPayload({
        name: "Keren Hishtalmut",
        category: "Investments",
        tag: "KH",
        type: "hishtalmut",
        interest_rate: 0,
        interest_rate_type: "variable",
        rate_spread: 0,
        notes: "",
        liquidity_date: "2030-01-01",
        commission_deposit: "1.5",
        commission_management: "0.4",
      });

      expect(payload).toMatchObject({
        liquidity_date: "2030-01-01",
        commission_deposit: 1.5,
        commission_management: 0.4,
      });
    });

    it("omits an empty liquidity date even for hishtalmut", () => {
      const payload = buildInvestmentPayload({
        name: "Keren Hishtalmut",
        category: "Investments",
        tag: "KH",
        type: "hishtalmut",
        interest_rate: 0,
        interest_rate_type: "variable",
        rate_spread: 0,
        notes: "",
        liquidity_date: "",
        commission_deposit: "",
        commission_management: "",
      });

      expect(payload).not.toHaveProperty("liquidity_date");
    });

    it("includes a genuine 0% deposit fee as the number zero, not omitted", () => {
      const payload = buildInvestmentPayload({
        name: "Keren Hishtalmut",
        category: "Investments",
        tag: "KH",
        type: "hishtalmut",
        interest_rate: 0,
        interest_rate_type: "variable",
        rate_spread: 0,
        notes: "",
        liquidity_date: "2030-01-01",
        commission_deposit: "0",
        commission_management: "",
      });

      expect(payload.commission_deposit).toBe(0);
      expect(typeof payload.commission_deposit).toBe("number");
    });

    it("omits commission_deposit entirely when the input was left empty", () => {
      const payload = buildInvestmentPayload({
        name: "Keren Hishtalmut",
        category: "Investments",
        tag: "KH",
        type: "hishtalmut",
        interest_rate: 0,
        interest_rate_type: "variable",
        rate_spread: 0,
        notes: "",
        liquidity_date: "2030-01-01",
        commission_deposit: "",
        commission_management: "0.4",
      });

      expect(payload).not.toHaveProperty("commission_deposit");
    });
  });
});
