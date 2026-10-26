import { describe, it, expect, vi, afterEach } from "vitest";
import { act, render, renderHook, screen } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useFirstLoadSettled } from "./useFirstLoadSettled";
import { DeferUntilVisible } from "../components/common/DeferUntilVisible";

/**
 * The dashboard's lower cards wait until they scroll near the viewport, but
 * "near" has to be measured once the cards above hold their real height —
 * on a cold load they are short skeletons and every placeholder looked near.
 */

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function withClient(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

describe("useFirstLoadSettled", () => {
  it("waits for the reads in flight, then latches", async () => {
    vi.useFakeTimers();
    const client = new QueryClient();
    let finish: (value: string) => void = () => {};
    void client.fetchQuery({
      queryKey: ["slow"],
      queryFn: () => new Promise<string>((resolve) => (finish = resolve)),
    });

    const { result } = renderHook(() => useFirstLoadSettled(), { wrapper: withClient(client) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current).toBe(false);

    await act(async () => {
      finish("done");
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(result.current).toBe(true);
  });

  it("gives up waiting after the fallback", async () => {
    vi.useFakeTimers();
    const client = new QueryClient();
    void client.fetchQuery({ queryKey: ["never"], queryFn: () => new Promise(() => {}) });

    const { result } = renderHook(() => useFirstLoadSettled(500), { wrapper: withClient(client) });
    await act(async () => {
      await vi.advanceTimersByTimeAsync(600);
    });
    expect(result.current).toBe(true);
  });
});

describe("DeferUntilVisible", () => {
  it("does not watch the viewport until armed", () => {
    const observe = vi.fn();
    vi.stubGlobal(
      "IntersectionObserver",
      class {
        observe = observe;
        disconnect() {}
      },
    );

    const { rerender } = render(
      <DeferUntilVisible armed={false}>
        <p>card</p>
      </DeferUntilVisible>,
    );
    expect(observe).not.toHaveBeenCalled();
    expect(screen.queryByText("card")).toBeNull();

    rerender(
      <DeferUntilVisible armed>
        <p>card</p>
      </DeferUntilVisible>,
    );
    expect(observe).toHaveBeenCalledTimes(1);
  });
});
