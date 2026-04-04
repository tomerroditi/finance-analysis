import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";
import { EarlyRetirement } from "./EarlyRetirement";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("EarlyRetirement", () => {
  describe("rendering", () => {
    it("renders the page title", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Early Retirement/i)).toBeInTheDocument();
      });
    });
  });

  describe("current status section", () => {
    it("displays financial status metrics", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Net Worth/i)).toBeInTheDocument();
      });
    });

    it("shows savings rate", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Savings Rate/i)).toBeInTheDocument();
      });
    });
  });

  describe("retirement goals section", () => {
    it("displays goal form with loaded data", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Retirement Goals/i)).toBeInTheDocument();
      });
    });

    it("shows Israeli savings vehicle fields", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Israeli Savings Vehicles/i)).toBeInTheDocument();
      });
    });
  });

  describe("projections section", () => {
    it("displays FIRE metrics", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getAllByText(/FIRE Number/i).length).toBeGreaterThan(0);
      });
    });

    it("shows readiness status", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Off Track/i)).toBeInTheDocument();
      });
    });
  });
});
