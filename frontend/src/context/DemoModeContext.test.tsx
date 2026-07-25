import { describe, expect, it } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { DemoModeProvider, useDemoMode } from "./DemoModeContext";
import { useQueryKeys } from "../hooks/useQueryKeys";
import { server } from "../mocks/server";

/** Records the demo flag that was in force on every render it performed. */
const seenFlags: boolean[] = [];

function Probe() {
  const { isDemoMode } = useDemoMode();
  const qk = useQueryKeys();
  seenFlags.push(isDemoMode);
  return <div data-testid="probe">{JSON.stringify(qk.analytics.overview())}</div>;
}

function renderGated() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <DemoModeProvider>
        <Probe />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

describe("DemoModeProvider", () => {
  // Every key from `useQueryKeys()` carries the demo flag as its LAST
  // segment. When the provider rendered children against its `false`
  // placeholder, a demo-mode user fetched everything twice — once under
  // [..., false] and again under [..., true] — and the demo response for
  // that first pass was cached (and persisted to IndexedDB, since it passes
  // shouldDehydrateQuery) under the REAL-mode key, where it could later
  // hydrate as the user's own data with demo mode off.
  it("renders nothing until the demo flag is known", async () => {
    seenFlags.length = 0;
    server.use(
      http.get("/api/testing/demo_mode_status", () =>
        HttpResponse.json({ demo_mode: true }),
      ),
    );

    renderGated();

    // Nothing below the provider has mounted yet, so no query key — and no
    // fetch — can exist under the wrong flag.
    expect(screen.queryByTestId("probe")).not.toBeInTheDocument();
    expect(seenFlags).toEqual([]);

    await waitFor(() =>
      expect(screen.getByTestId("probe")).toBeInTheDocument(),
    );

    expect(seenFlags.every((flag) => flag === true)).toBe(true);
    expect(screen.getByTestId("probe").textContent).toContain("true");
  });

  it("still renders (in real mode) when the status request fails", async () => {
    seenFlags.length = 0;
    server.use(
      http.get("/api/testing/demo_mode_status", () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 }),
      ),
    );

    renderGated();

    await waitFor(() =>
      expect(screen.getByTestId("probe")).toBeInTheDocument(),
    );
    expect(seenFlags.every((flag) => flag === false)).toBe(true);
  });

  it("skips the gate when the flag is supplied up front (test harness)", () => {
    seenFlags.length = 0;
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={queryClient}>
        <DemoModeProvider initialDemoMode={false}>
          <Probe />
        </DemoModeProvider>
      </QueryClientProvider>,
    );
    expect(screen.getByTestId("probe")).toBeInTheDocument();
  });
});
