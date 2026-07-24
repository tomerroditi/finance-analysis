import { describe, it, expect } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "../test-utils";
import { server } from "../mocks/server";
import { mockRetirementProjections } from "../mocks/handlers";
import { makeQueryKeys } from "../services/queryKeys";
import type { RetirementProjections } from "../services/api";
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

  describe("calculate preview", () => {
    // Regression: the preview POST results were written into the SAVED-plan
    // query keys from inside a `useMutation`. The global
    // `MutationCache.onSuccess` in queryClient.ts then ran
    // `invalidateQueries()` 200 ms later, refetching GET
    // /retirement/projections and overwriting the preview with the saved
    // plan — the user saw new numbers flash, then a skeleton, then the OLD
    // numbers. Previews are page state now; nothing can invalidate them.
    const PREVIEW_FIRE_NUMBER = 7_777_777;

    // happy-dom does not implement implicit form submission from a submit
    // button click, so drive the form's submit event directly.
    function submitCalculate() {
      const button = screen.getByRole("button", { name: /Calculate/i });
      expect(button).toBeEnabled();
      fireEvent.submit(button.closest("form")!);
    }

    function usePreviewHandlers() {
      server.use(
        http.post("/api/retirement/projections", () =>
          HttpResponse.json({
            ...mockRetirementProjections,
            fire_number: PREVIEW_FIRE_NUMBER,
          }),
        ),
      );
    }

    it("shows the preview and survives a full cache invalidation", async () => {
      usePreviewHandlers();
      const { container, queryClient } = renderWithProviders(
        <EarlyRetirement />,
      );

      // Saved plan lands first.
      await waitFor(() =>
        expect(container.textContent).toContain("3,600,000"),
      );

      submitCalculate();
      await waitFor(() =>
        expect(container.textContent).toContain("7,777,777"),
      );

      // Exactly what the global invalidator does 200 ms after any mutation.
      await act(async () => {
        await queryClient.invalidateQueries();
      });

      expect(container.textContent).toContain("7,777,777");
      expect(container.textContent).not.toContain("3,600,000");
    });

    it("leaves the saved-plan cache entry untouched", async () => {
      usePreviewHandlers();
      const { container, queryClient } = renderWithProviders(
        <EarlyRetirement />,
      );
      await waitFor(() =>
        expect(container.textContent).toContain("3,600,000"),
      );

      submitCalculate();
      await waitFor(() =>
        expect(container.textContent).toContain("7,777,777"),
      );

      const saved = queryClient.getQueryData<RetirementProjections>(
        makeQueryKeys(false).retirement.projections(),
      );
      expect(saved?.fire_number).toBe(mockRetirementProjections.fire_number);
    });
  });
});
