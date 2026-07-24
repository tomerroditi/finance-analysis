import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";

import { DialogProvider, useDialog } from "./DialogContext";

type DialogApi = ReturnType<typeof useDialog>;

/** Publishes the context API so tests can drive it imperatively. */
function Harness({ onReady }: { onReady: (api: DialogApi) => void }) {
  onReady(useDialog());
  return null;
}

function renderDialogs() {
  let api!: DialogApi;
  render(
    <DialogProvider>
      <Harness
        onReady={(value) => {
          api = value;
        }}
      />
    </DialogProvider>,
  );
  return () => api;
}

describe("DialogProvider notifications", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("dismisses a toast after its own duration", async () => {
    const api = renderDialogs();

    act(() => api().notify({ message: "first", duration: 4500 }));
    expect(screen.getByText("first")).toBeInTheDocument();

    await act(async () => {
      await vi.advanceTimersByTimeAsync(4600);
    });
    expect(screen.queryByText("first")).not.toBeInTheDocument();
  });

  // Regression: NotificationStack passed a fresh `() => onDismiss(n.id)`
  // closure on every render, so the toast's auto-dismiss effect re-ran (and
  // restarted its 4.5 s timer) every time ANY other toast appeared or
  // disappeared. A steady trickle of toasts kept the earlier ones on screen
  // essentially forever.
  it("does not restart a visible toast's timer when another toast arrives", async () => {
    const api = renderDialogs();

    act(() => api().notify({ message: "first", duration: 4500 }));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000);
    });
    act(() => api().notify({ message: "second", duration: 4500 }));

    // 1.6 s later the first toast is past its own 4.5 s budget and must be
    // gone, even though the second one is still on screen.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1600);
    });
    expect(screen.queryByText("first")).not.toBeInTheDocument();
    expect(screen.getByText("second")).toBeInTheDocument();
  });

  it("keeps a toast with duration <= 0 on screen", async () => {
    const api = renderDialogs();
    act(() => api().notify({ message: "sticky", duration: 0 }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(screen.getByText("sticky")).toBeInTheDocument();
  });
});

describe("DialogProvider confirm", () => {
  // Regression: a second confirm() while one was pending overwrote
  // `confirmState` and dropped the first entry's `resolve`, so that caller's
  // `await confirm(...)` never settled and its handler silently died
  // half-way through. Confirms are queued now.
  it("resolves every queued confirm, in order", async () => {
    const api = renderDialogs();
    const settled: string[] = [];

    let firstPromise!: Promise<boolean>;
    let secondPromise!: Promise<boolean>;
    act(() => {
      firstPromise = api().confirm({ message: "delete the first thing" });
      secondPromise = api().confirm({ message: "delete the second thing" });
    });
    void firstPromise.then((v) => settled.push(`first:${v}`));
    void secondPromise.then((v) => settled.push(`second:${v}`));

    // Only the head of the queue is on screen.
    expect(screen.getByText("delete the first thing")).toBeInTheDocument();
    expect(
      screen.queryByText("delete the second thing"),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Confirm" }));
    await waitFor(() =>
      expect(screen.getByText("delete the second thing")).toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(settled).toHaveLength(2));

    expect(settled).toEqual(["first:true", "second:false"]);
    await waitFor(() =>
      expect(
        screen.queryByText("delete the second thing"),
      ).not.toBeInTheDocument(),
    );
  });

  it("resolves a single confirm with false when cancelled", async () => {
    const api = renderDialogs();
    let promise!: Promise<boolean>;
    act(() => {
      promise = api().confirm({ message: "are you sure" });
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    await expect(promise).resolves.toBe(false);
  });
});
