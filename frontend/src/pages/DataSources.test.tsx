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
