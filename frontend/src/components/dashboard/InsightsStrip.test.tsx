import { describe, it, expect, vi, beforeEach } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { InsightsStrip } from "./InsightsStrip";
import { analyticsApi, testingApi, type Insight } from "../../services/api";
import { DemoModeProvider } from "../../context/DemoModeContext";

/**
 * The strip's job is to carry what no other dashboard card says. Insights that
 * restate a visible card (the "This Month" hero, the Subscriptions panel) are
 * dropped here rather than in the backend, which cannot see the browser-local
 * layout — so these tests pin that filter, and the per-card dismiss button.
 */

// The layout hook memoizes its localStorage read in module state, so seeding
// storage per test would not take effect after the first render. The strip only
// needs to know which cards are hidden, so that is what the mock provides.
let hiddenCards: string[] = [];
vi.mock("../../hooks/useDashboardLayout", () => ({
  useDashboardLayout: () => ({ layout: { order: [], hidden: hiddenCards } }),
}));

function makeInsight(overrides: Partial<Insight> = {}): Insight {
  return {
    code: "categorySpike",
    key: "categorySpike:Food:2026-09",
    severity: "warning",
    data: { category: "Food", percent: 60, amount: 1500 },
    ...overrides,
  };
}

async function renderStrip(insights: Insight[]) {
  vi.spyOn(analyticsApi, "getInsights").mockResolvedValue({
    data: insights,
  } as Awaited<ReturnType<typeof analyticsApi.getInsights>>);
  vi.spyOn(testingApi, "getDemoModeStatus").mockResolvedValue({
    data: { demo_mode: false, forced: false },
  } as Awaited<ReturnType<typeof testingApi.getDemoModeStatus>>);

  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DemoModeProvider>
        <InsightsStrip />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.restoreAllMocks();
  hiddenCards = [];
});

describe("InsightsStrip", () => {
  describe("cards another visible card already carries", () => {
    it("drops the pace card while the forecast hero is on the dashboard", async () => {
      hiddenCards = ["recurring"];
      await renderStrip([
        makeInsight(),
        makeInsight({
          code: "onTrack",
          key: "onTrack:2026-09",
          severity: "positive",
          data: { amount: 2000 },
        }),
      ]);

      await screen.findByText(/Food/);
      expect(screen.queryByText(/On track to save/i)).toBeNull();
    });

    it("keeps the pace card once the forecast hero is hidden", async () => {
      hiddenCards = ["forecast", "recurring"];
      await renderStrip([
        makeInsight({
          code: "onTrack",
          key: "onTrack:2026-09",
          severity: "positive",
          data: { amount: 2000 },
        }),
      ]);

      expect(await screen.findByText(/On track to save/i)).toBeTruthy();
    });

    it("drops the recurring cards while the subscriptions panel is visible", async () => {
      hiddenCards = [];
      await renderStrip([
        makeInsight({
          code: "recurringToReview",
          key: "recurringToReview:2026-09",
          severity: "info",
          data: { count: 4, amount: 300 },
        }),
      ]);

      await waitFor(() => {
        expect(screen.queryByTestId("insight-card")).toBeNull();
      });
    });
  });

  describe("dismissing", () => {
    it("posts the card's key and offers a way back", async () => {
      hiddenCards = ["forecast", "recurring"];
      const dismiss = vi
        .spyOn(analyticsApi, "dismissInsight")
        .mockResolvedValue({
          data: { key: "categorySpike:Food:2026-09", dismissed: true },
        } as Awaited<ReturnType<typeof analyticsApi.dismissInsight>>);
      const restore = vi
        .spyOn(analyticsApi, "restoreInsight")
        .mockResolvedValue({
          data: { key: "categorySpike:Food:2026-09", dismissed: false },
        } as Awaited<ReturnType<typeof analyticsApi.restoreInsight>>);

      await renderStrip([makeInsight()]);
      fireEvent.click(await screen.findByTestId("insight-dismiss"));

      await waitFor(() => {
        expect(dismiss).toHaveBeenCalledWith("categorySpike:Food:2026-09");
      });

      const undo = await screen.findByRole("button", { name: /undo/i });
      fireEvent.click(undo);
      await waitFor(() => {
        expect(restore).toHaveBeenCalledWith("categorySpike:Food:2026-09");
      });
    });
  });
});
