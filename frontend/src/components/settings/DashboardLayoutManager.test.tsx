import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { DashboardLayoutManager } from "./DashboardLayoutManager";
import type { DashboardCardId } from "../../hooks/useDashboardLayout";
import type * as DashboardLayoutModule from "../../hooks/useDashboardLayout";

// Mock useDashboardLayout so the test uses a known layout with both half-width
// and full-width cards visible, independent of localStorage cache state.
vi.mock("../../hooks/useDashboardLayout", async (importOriginal) => {
  const actual = await importOriginal<typeof DashboardLayoutModule>();
  return {
    ...actual,
    useDashboardLayout: () => ({
      layout: {
        // budget + recent are half-width; heatmap + charts are full-width
        order: ["budget", "recent", "heatmap", "charts"] as DashboardCardId[],
        hidden: [] as DashboardCardId[],
      },
      setOrder: vi.fn(),
      toggleHidden: vi.fn(),
      reset: vi.fn(),
    }),
  };
});

describe("DashboardLayoutManager", () => {
  beforeEach(() => {
    localStorage.removeItem("fa.dashboard.layout");
  });

  it("renders Half width and Full width size badges for visible cards", () => {
    // The default visible layout has budget + recent (half) and heatmap + charts
    // (full). Each card row renders a SizeBadge showing its translated label.
    renderWithProviders(<DashboardLayoutManager />);

    const halfBadges = screen.getAllByText("Half width");
    const fullBadges = screen.getAllByText("Full width");

    expect(halfBadges.length).toBeGreaterThanOrEqual(2);
    expect(fullBadges.length).toBeGreaterThanOrEqual(2);
  });
});
