import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import {
  DemoModeProvider,
  useDemoMode,
  DEMO_MODE_STORAGE_KEY,
} from "./DemoModeContext";

function Probe() {
  const { isDemoMode } = useDemoMode();
  return <span data-testid="flag">{String(isDemoMode)}</span>;
}

function renderProbe() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <DemoModeProvider>
        <Probe />
      </DemoModeProvider>
    </QueryClientProvider>,
  );
}

describe("DemoModeProvider", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("renders children immediately without waiting for the status request", () => {
    renderProbe();
    expect(screen.getByTestId("flag")).toBeInTheDocument();
  });

  it("reads the stored flag synchronously on mount", () => {
    localStorage.setItem(DEMO_MODE_STORAGE_KEY, "1");
    renderProbe();
    expect(screen.getByTestId("flag")).toHaveTextContent("true");
  });

  it("defaults to real mode when nothing is stored", () => {
    renderProbe();
    expect(screen.getByTestId("flag")).toHaveTextContent("false");
  });

  it("adopts the server value when the deployment forces demo mode", async () => {
    server.use(
      http.get("/api/testing/demo_mode_status", () =>
        HttpResponse.json({ demo_mode: true, forced: true }),
      ),
    );
    renderProbe();
    await waitFor(() =>
      expect(screen.getByTestId("flag")).toHaveTextContent("true"),
    );
  });

  it("ignores the server value when the deployment does not force it", async () => {
    server.use(
      http.get("/api/testing/demo_mode_status", () =>
        HttpResponse.json({ demo_mode: true, forced: false }),
      ),
    );
    renderProbe();
    await waitFor(() =>
      expect(screen.getByTestId("flag")).toHaveTextContent("false"),
    );
  });
});
