import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RecurringSection } from "./RecurringSection";
import {
  analyticsApi,
  testingApi,
  type RecurringItem,
  type RecurringSummary,
} from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * The card's job is to let a verdict be given, taken back, and seen landing
 * at once. A verdict invalidates every derived read on the dashboard, so the
 * round trip is long — these pin that the card answers the click from its own
 * arithmetic rather than waiting for it, and that a charge which has stopped
 * billing stays out of the way.
 */

function makeItem(overrides: Partial<RecurringItem> = {}): RecurringItem {
  return {
    label: "NETFLIX.COM",
    normalized: "netflix com",
    amount: 45,
    last_amount: 45,
    cadence: "monthly",
    period_days: 30,
    monthly_equivalent: 45,
    occurrences: 6,
    category: "Entertainment",
    first_date: "2026-03-01",
    last_date: "2026-09-01",
    next_expected_date: "2026-10-01",
    status: "active",
    price_change: 0,
    confirmation: "pending",
    confidence: 0.9,
    amount_kind: "fixed",
    ...overrides,
  };
}

function makeSummary(items: RecurringItem[]): RecurringSummary {
  const live = items.filter((i) => i.status !== "ended");
  const sum = (confirmation: string) =>
    live
      .filter((i) => i.confirmation === confirmation)
      .reduce((total, i) => total + i.monthly_equivalent, 0);
  return {
    items,
    total_monthly: sum("confirmed"),
    pending_monthly: sum("pending"),
    pending_count: items.filter((i) => i.confirmation === "pending").length,
    confirmed_count: items.filter((i) => i.confirmation === "confirmed").length,
    dismissed_count: items.filter((i) => i.confirmation === "dismissed").length,
  };
}

/**
 * Render the card over a summary that *remembers* verdicts, so the refetch
 * every verdict triggers answers with what was just stored — a mock that
 * replayed the original list would undo the optimistic patch and hide the
 * very bug these tests are for.
 *
 * Pass `decide` to control the POST (reject it, or never resolve it).
 */
async function renderCard(
  items: RecurringItem[],
  decide?: ReturnType<typeof vi.fn>,
) {
  let stored = items;
  vi.spyOn(analyticsApi, "getRecurring").mockImplementation(
    async (includeDismissed = false) =>
      ({
        data: makeSummary(
          includeDismissed
            ? stored
            : stored.filter((i) => i.confirmation !== "dismissed"),
        ),
      }) as Awaited<ReturnType<typeof analyticsApi.getRecurring>>,
  );
  vi.spyOn(analyticsApi, "setRecurringDecisions").mockImplementation(
    decide ??
      (async (decisions) => {
        const verdicts = new Map(
          decisions.map((d) => [d.normalized, d.decision]),
        );
        stored = stored.map((i) =>
          verdicts.has(i.normalized)
            ? { ...i, confirmation: verdicts.get(i.normalized)! }
            : i,
        );
        return { data: { updated: decisions } } as Awaited<
          ReturnType<typeof analyticsApi.setRecurringDecisions>
        >;
      }),
  );
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <RecurringSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("RecurringSection", () => {
  describe("a verdict shows without waiting for the round trip", () => {
    it("moves a confirmed candidate before the request resolves", async () => {
      // Never resolves: anything the card shows is its own arithmetic.
      const decide = vi.fn(() => new Promise(() => {}));
      await renderCard([makeItem()], decide);

      fireEvent.click(await screen.findByTestId("recurring-pending-item"));
      fireEvent.click(
        screen.getByRole("button", { name: /Confirm .* as recurring/i }),
      );

      await waitFor(() => {
        expect(screen.queryByTestId("recurring-pending-item")).toBeNull();
      });
      expect(screen.getByTestId("recurring-confirmed-item")).toBeTruthy();
      expect(decide).toHaveBeenCalledWith([
        { normalized: "netflix com", decision: "confirmed" },
      ]);
    });

    it("moves the monthly total at the same moment", async () => {
      await renderCard([makeItem()], vi.fn(() => new Promise(() => {})));

      fireEvent.click(await screen.findByTestId("recurring-pending-item"));
      fireEvent.click(
        screen.getByRole("button", { name: /Confirm .* as recurring/i }),
      );

      await waitFor(() => {
        expect(screen.getByTestId("recurring-total").textContent).toMatch(/45/);
      });
    });

    it("puts the candidate back when the request fails", async () => {
      const decide = vi.fn().mockRejectedValue(new Error("offline"));
      await renderCard([makeItem()], decide);

      fireEvent.click(await screen.findByTestId("recurring-pending-item"));
      fireEvent.click(
        screen.getByRole("button", { name: /Confirm .* as recurring/i }),
      );

      await waitFor(() => expect(decide).toHaveBeenCalled());
      await waitFor(() => {
        expect(screen.getByTestId("recurring-pending-item")).toBeTruthy();
      });
    });
  });

  describe("charges that have ended", () => {
    it("keeps them out of the list until they are asked for", async () => {
      await renderCard([
        makeItem({ confirmation: "confirmed" }),
        makeItem({
          label: "GITHUB INC",
          normalized: "github inc",
          status: "ended",
          confirmation: "confirmed",
        }),
      ]);

      expect(await screen.findByText("NETFLIX.COM")).toBeTruthy();
      expect(screen.queryByText("GITHUB INC")).toBeNull();

      fireEvent.click(screen.getByTestId("recurring-toggle-ended"));
      expect(await screen.findByText("GITHUB INC")).toBeTruthy();
    });

    it("still offers the way back when every charge has ended", async () => {
      await renderCard([
        makeItem({ status: "ended", confirmation: "confirmed" }),
      ]);

      const toggle = await screen.findByTestId("recurring-toggle-ended");
      expect(toggle.textContent).toContain("1");
      fireEvent.click(toggle);
      expect(await screen.findByText("NETFLIX.COM")).toBeTruthy();
    });
  });

  describe("taking a confirmed charge back", () => {
    it("removes it outright, without a trip through review", async () => {
      await renderCard([makeItem({ confirmation: "confirmed" })]);

      fireEvent.click(await screen.findByTestId("recurring-remove"));

      await waitFor(() => {
        expect(analyticsApi.setRecurringDecisions).toHaveBeenCalledWith([
          { normalized: "netflix com", decision: "dismissed" },
        ]);
      });
      await waitFor(() => {
        expect(screen.queryByTestId("recurring-confirmed-item")).toBeNull();
      });
      expect(screen.queryByTestId("recurring-pending-item")).toBeNull();
    });
  });
});
