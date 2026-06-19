import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { createElement } from "react";
import { useScraping } from "./useScraping";
import { scrapingApi } from "../services/api";

vi.mock("../services/api", () => ({
  scrapingApi: {
    start: vi.fn().mockResolvedValue({ data: 1 }),
    getStatus: vi.fn().mockResolvedValue({ data: { status: "in_progress" } }),
    abort: vi.fn().mockResolvedValue({ data: { status: "aborted" } }),
    submit2fa: vi.fn().mockResolvedValue({ data: { status: "success" } }),
  },
}));

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient();
  return createElement(QueryClientProvider, { client: qc }, children);
}

const acc = { service: "banks", provider: "onezero", account_name: "Acc" };

describe("useScraping.startScraper force2fa", () => {
  beforeEach(() => vi.clearAllMocks());

  it("sends force_2fa: true when opts.force2fa is set", async () => {
    const { result } = renderHook(() => useScraping(), { wrapper });
    await act(async () => {
      await result.current.startScraper(acc, 30, { force2fa: true });
    });
    await waitFor(() =>
      expect(scrapingApi.start).toHaveBeenCalledWith(
        expect.objectContaining({
          service: "banks",
          provider: "onezero",
          account: "Acc",
          scraping_period_days: 30,
          force_2fa: true,
        }),
      ),
    );
  });

  it("omits force_2fa when no opts are passed", async () => {
    const { result } = renderHook(() => useScraping(), { wrapper });
    await act(async () => {
      await result.current.startScraper(acc, null);
    });
    await waitFor(() => expect(scrapingApi.start).toHaveBeenCalledTimes(1));
    const payload = (scrapingApi.start as unknown as ReturnType<typeof vi.fn>)
      .mock.calls[0][0];
    expect(payload.force_2fa).toBeUndefined();
  });
});
