import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import {
  MutationCache,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query";
import { RecurringSection } from "./RecurringSection";
import {
  analyticsApi,
  testingApi,
  type RecurringDecisionInput,
  type RecurringItem,
  type RecurringSummary,
} from "../../services/api";
import { createInvalidationSweep } from "../../queryInvalidation";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * A confirmed charge must never undo itself.
 *
 * Every successful verdict schedules the app-wide sweep, which refetches the
 * card. Give a second verdict while that sweep is still queued and the read
 * it fires can be answered from the state *before* that second write — so
 * the payload that lands is one where the charge is still pending. Nothing
 * about the card's own arithmetic prevents that; what does is that the
 * request which started before the click is cancelled, and that the one
 * after it reads post-write state.
 *
 * This drives the real sweep from `queryInvalidation.ts` (the same function
 * `queryClient.ts` wires up) rather than a bare client, because the ordering
 * between sweep, read and write is the whole point.
 */

const SWEEP_MS = 20;

function makeItem(overrides: Partial<RecurringItem> = {}): RecurringItem {
  return {
    label: "NETFLIX.COM",
    normalized: "netflix",
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

function summaryOf(items: RecurringItem[]): RecurringSummary {
  const live = items.filter((i) => i.status !== "ended");
  const sum = (c: string) =>
    live
      .filter((i) => i.confirmation === c)
      .reduce((t, i) => t + i.monthly_equivalent, 0);
  return {
    items,
    total_monthly: sum("confirmed"),
    pending_monthly: sum("pending"),
    pending_count: items.filter((i) => i.confirmation === "pending").length,
    confirmed_count: items.filter((i) => i.confirmation === "confirmed").length,
    dismissed_count: 0,
  };
}

const flush = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** How many writes the fake backend has applied so far. */
let committed = 0;

/**
 * A backend that answers a read from the state it held **when the read
 * started**, and applies a write only after `writeMs`. That is what a real
 * server does — detection runs against the rows as they were when the
 * request arrived — and it is the whole reason a read issued mid-write can
 * come back carrying pre-write data.
 */
function fakeBackend(initial: RecurringItem[], writeMs: number) {
  let stored = initial;
  committed = 0;
  vi.spyOn(analyticsApi, "getRecurring").mockImplementation(async () => {
    const asOf = stored;
    await flush(5);
    return { data: summaryOf(asOf) } as Awaited<
      ReturnType<typeof analyticsApi.getRecurring>
    >;
  });
  vi.spyOn(analyticsApi, "setRecurringDecisions").mockImplementation(
    (async (decisions: RecurringDecisionInput[]) => {
      await flush(writeMs);
      const verdicts = new Map(decisions.map((d) => [d.normalized, d.decision]));
      stored = stored.map((i) =>
        verdicts.has(i.normalized)
          ? { ...i, confirmation: verdicts.get(i.normalized)! }
          : i,
      );
      committed += 1;
      return { data: { updated: decisions } };
    }) as unknown as typeof analyticsApi.setRecurringDecisions,
  );
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);
}

/** Render the card behind the app's real post-mutation sweep. */
function renderWithSweep() {
  const mutationCache = new MutationCache({
    onSuccess: () => sweep(),
  });
  const client = new QueryClient({
    mutationCache,
    defaultOptions: { queries: { retry: false, staleTime: 5 * 60_000 } },
  });
  const sweep = createInvalidationSweep(client, SWEEP_MS);
  return render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <RecurringSection />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

const confirmButtons = () =>
  screen.getAllByRole("button", { name: /Confirm .* as recurring/i });

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("RecurringSection — a verdict racing the previous verdict's sweep", () => {
  it("keeps the second confirmation when the sweep's read predates it", async () => {
    // The second write outlives the sweep the first one scheduled, so the
    // sweep's refetch is answered before the second verdict is stored.
    fakeBackend(
      [
        makeItem(),
        makeItem({
          label: "SPOTIFY",
          normalized: "spotify",
          monthly_equivalent: 20,
        }),
      ],
      SWEEP_MS * 6,
    );
    renderWithSweep();

    await waitFor(() => expect(confirmButtons()).toHaveLength(2));
    fireEvent.click(confirmButtons()[0]);

    // Wait until the first write has actually landed — that is what schedules
    // the sweep — and only then give the second verdict, so the sweep fires
    // while the second write is still in flight. That ordering is the whole
    // scenario: the sweep's read is answered before the second write lands.
    await waitFor(() => expect(committed).toBe(1));
    fireEvent.click(confirmButtons()[0]);

    await waitFor(() =>
      expect(screen.getAllByTestId("recurring-confirmed-item")).toHaveLength(2),
    );

    // Let every sweep, refetch and write settle. Both verdicts must survive:
    // the charge must not drift back into the review block on its own.
    await flush(SWEEP_MS * 20);
    await waitFor(() => {
      expect(screen.queryAllByTestId("recurring-pending-item")).toHaveLength(0);
    });
    expect(screen.getAllByTestId("recurring-confirmed-item")).toHaveLength(2);
    expect(screen.getByTestId("recurring-total").textContent).toMatch(/65/);
  });
});
