import { describe, it, expect, beforeEach } from "vitest";
import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "../test-utils";
import { server } from "../mocks/server";
import { mockRetirementProjections } from "../mocks/handlers";
import { makeQueryKeys } from "../services/queryKeys";
import type { RetirementProjections } from "../services/api";
import { useRetirementWorkspaceStore } from "../stores/retirementWorkspaceStore";
import { EarlyRetirement } from "./EarlyRetirement";

describe("EarlyRetirement", () => {
  // The workspace store is module-global — reset it so tests stay isolated.
  beforeEach(() => {
    useRetirementWorkspaceStore.getState().clear();
  });
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
      // "Net Worth" also appears in chart headings and tooltip copy —
      // assert at least one element renders it.
      await waitFor(() => {
        expect(screen.getAllByText(/Net Worth/i).length).toBeGreaterThan(0);
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
        // Labels also appear inside the info-tooltip copy — getAllByText
        // asserts at least one element is present.
        expect(
          screen.getAllByText(/Keren Hishtalmut Balance/i).length,
        ).toBeGreaterThan(0);
        expect(screen.getAllByText(/Monthly Pension/i).length).toBeGreaterThan(0);
      });
    });
  });

  describe("scraped auto-fill", () => {
    // Regression: scraped amounts are fractional (averages, agorot) but the
    // currency inputs are whole-shekel (implicit step=1). An unrounded fill
    // left the input browser-invalid ("Please enter a valid value…").
    it("rounds fractional scraped values to whole shekels; deposit never fills pension payout", async () => {
      server.use(
        http.get("/api/retirement/goal", () => HttpResponse.json(null)),
        http.get("/api/retirement/scraped-defaults", () =>
          HttpResponse.json({
            keren_hishtalmut_balance: 255000.55,
            keren_hishtalmut_monthly_contribution: 2971.33,
            pension_monthly_deposit: 1571.44,
            avg_monthly_salary: 31092.73833333333,
          }),
        ),
      );
      renderWithProviders(<EarlyRetirement />);

      const inputValues = () =>
        screen
          .getAllByRole("spinbutton")
          .map((el) => (el as HTMLInputElement).value);

      // The auto-fill lands once the scraped defaults arrive — rounded.
      await waitFor(() => expect(inputValues()).toContain("31093"));
      const values = inputValues();
      expect(values).toContain("255001");
      expect(values).toContain("2971");
      expect(values).not.toContain("31092.73833333333");
      expect(values).not.toContain("255000.55");
      expect(values).not.toContain("2971.33");
      // The pension DEPOSIT (contribution into the fund) must never be
      // auto-filled into the pension PAYOUT estimate.
      expect(values).not.toContain("1571");
      expect(values).not.toContain("1571.44");
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

    // Regression: the projections section rendered a skeleton whenever the
    // query was merely REFETCHING (window refocus after staleTime, the
    // global post-mutation sweep) — every return to the tab looked like a
    // full page reload. Cached values must stay on screen.
    it("keeps cached projections on screen during a background refetch", async () => {
      const { container, queryClient } = renderWithProviders(
        <EarlyRetirement />,
      );
      await waitFor(() =>
        expect(container.textContent).toContain("3,600,000"),
      );

      act(() => {
        void queryClient.invalidateQueries();
      });

      // Synchronously after invalidation the query is fetching — the page
      // must still show the cached numbers, not a skeleton.
      expect(container.textContent).toContain("3,600,000");
    });

    // Regression: the Calculate preview and form edits lived in component
    // state, so navigating to another page (which unmounts this one) wiped
    // them — every re-entry looked like a full page reload. The session
    // workspace store must restore the preview on remount.
    it("keeps the Calculate preview across unmount/remount (route navigation)", async () => {
      usePreviewHandlers();
      const first = renderWithProviders(<EarlyRetirement />);
      await waitFor(() =>
        expect(first.container.textContent).toContain("3,600,000"),
      );
      submitCalculate();
      await waitFor(() =>
        expect(first.container.textContent).toContain("7,777,777"),
      );

      // Simulate route navigation: unmount the page, then mount it fresh.
      first.unmount();
      const second = renderWithProviders(<EarlyRetirement />);

      // The preview is back immediately and still shadows the saved plan.
      await waitFor(() =>
        expect(second.container.textContent).toContain("7,777,777"),
      );
      expect(second.container.textContent).not.toContain("3,600,000");
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
