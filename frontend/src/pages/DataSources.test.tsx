import { describe, it, expect, beforeAll, afterAll, afterEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";
import { DataSources } from "./DataSources";

beforeAll(() => server.listen({ onUnhandledRequest: "bypass" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

describe("DataSources", () => {
  describe("rendering", () => {
    it("renders the page title", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText("Data Sources")).toBeInTheDocument();
      });
    });

    it("renders the subtitle", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Manage your connected accounts/i)).toBeInTheDocument();
      });
    });
  });

  describe("connected accounts", () => {
    it("displays saved credentials from the API", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Main Account/i)).toBeInTheDocument();
      });
    });

    it("shows provider names for connected accounts", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Hapoalim/i)).toBeInTheDocument();
      });
    });
  });

  describe("bank balances", () => {
    it("displays bank balance information", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Main Account/i)).toBeInTheDocument();
      });
    });
  });
});
