import { describe, it, expect, beforeEach } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { useMoneyBasis } from "./useMoneyBasis";

describe("useMoneyBasis", () => {
  beforeEach(() => {
    window.localStorage.removeItem("fa.moneyBasis");
  });

  it("starts on net cost", () => {
    const { result } = renderHook(() => useMoneyBasis());

    expect(result.current.basis).toBe("net_cost");
  });

  it("is shared: one setter moves every reader and is remembered", () => {
    const first = renderHook(() => useMoneyBasis());
    const second = renderHook(() => useMoneyBasis());

    act(() => first.result.current.setBasis("cash_flow"));

    expect(second.result.current.basis).toBe("cash_flow");
    expect(window.localStorage.getItem("fa.moneyBasis")).toBe("cash_flow");
  });

  it("ignores a stored value it does not know", () => {
    window.localStorage.setItem("fa.moneyBasis", "accrual");

    expect(renderHook(() => useMoneyBasis()).result.current.basis).toBe("net_cost");
  });
});
