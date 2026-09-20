import { describe, it, expect } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { usePendingRows } from "./usePendingRows";

/**
 * A list shares one mutation, so its `isPending` is true for every row while
 * any one row is being written. Gating each row's button on that locks the
 * whole list for the length of the write — seconds on a real database — and
 * clicks on the other rows land on dead buttons and are silently dropped.
 */

describe("usePendingRows", () => {
  it("reports only the rows actually being written", () => {
    const { result } = renderHook(() => usePendingRows());

    act(() => result.current.begin("bank_1"));

    expect(result.current.isPending("bank_1")).toBe(true);
    expect(result.current.isPending("bank_2")).toBe(false);
  });

  it("tracks several rows at once", () => {
    // `TransactionsTable` unlinks every refund link of a transaction in a
    // loop, so more than one write really is in flight — which is why this
    // holds a set rather than the mutation's own `variables`, which only
    // ever carries the most recent call.
    const { result } = renderHook(() => usePendingRows<number>());

    act(() => {
      result.current.begin(1);
      result.current.begin(2);
    });
    expect([1, 2, 3].map(result.current.isPending)).toEqual([true, true, false]);

    act(() => result.current.end(1));
    expect([1, 2].map(result.current.isPending)).toEqual([false, true]);
  });

  it("releases a row whether the write succeeded or failed", () => {
    // Wired to the mutation's `onSettled`, so a rejected write must not
    // leave its row disabled for the rest of the session.
    const { result } = renderHook(() => usePendingRows());

    act(() => result.current.begin("row"));
    act(() => result.current.end("row"));

    expect(result.current.isPending("row")).toBe(false);
  });

  it("ignores an end for a row it is not holding", () => {
    const { result } = renderHook(() => usePendingRows());
    const before = result.current.isPending;

    act(() => result.current.end("never-began"));

    // No state change, so no re-render and no new identity to churn effects.
    expect(result.current.isPending).toBe(before);
  });
});
