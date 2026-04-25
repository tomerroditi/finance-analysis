import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { EarlyRetirement } from "./EarlyRetirement";

describe("EarlyRetirement", () => {
  describe("current status section", () => {
    it("renders the current financial status section", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(
          screen.getByText(/Current Financial Status/i),
        ).toBeInTheDocument();
      });
    });

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
    it("displays the retirement goals section header", async () => {
      renderWithProviders(<EarlyRetirement />);
      await waitFor(() => {
        expect(screen.getByText(/Retirement Goals/i)).toBeInTheDocument();
      });
    });

    it("renders Israeli savings vehicle form fields", async () => {
      renderWithProviders(<EarlyRetirement />);
      // The "Israeli Savings Vehicles" cluster on the form renders
      // dedicated inputs for Keren Hishtalmut and Monthly Pension.
      await waitFor(() => {
        expect(
          screen.getByText(/Keren Hishtalmut Balance/i),
        ).toBeInTheDocument();
        // "Monthly Pension" appears in both the form label and the
        // breakdown table — getAllByText asserts at least one is present.
        expect(screen.getAllByText(/Monthly Pension/i).length).toBeGreaterThan(0);
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
