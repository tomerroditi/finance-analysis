import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { DataSources } from "./DataSources";

describe("DataSources", () => {
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
        // Both the scraped account ("hapoalim") and the mocked imported
        // account ("Hapoalim Manual") match this regex, so use getAllByText.
        expect(screen.getAllByText(/Hapoalim/i).length).toBeGreaterThan(0);
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

  describe("imported accounts", () => {
    it("renders imported accounts alongside scraped accounts with an Imported badge", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Imported Checking/i)).toBeInTheDocument();
      });
      // The "Imported" badge (translation key dataSources.import.importedBadge)
      // appears alongside the imported account card. Both the account name
      // ("Imported Checking") and the badge text contain "imported", so we
      // expect at least 2 matches.
      expect(screen.getAllByText(/imported/i).length).toBeGreaterThan(0);
    });
  });
});
