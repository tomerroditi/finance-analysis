import { useCallback, useSyncExternalStore } from "react";

/**
 * How the dashboard counts income and spending — the backend's `basis`
 * (`backend/services/cash_flow_basis.py`):
 * - `net_cost`: what things cost. Purchases on the day bought, refunds taken
 *   off what they repay.
 * - `cash_flow`: money as it moved. Card purchases on the day the card charged
 *   the bank, refunds as income on the day they arrived.
 */
export type MoneyBasis = "net_cost" | "cash_flow";

const KEY = "fa.moneyBasis";
const DEFAULT_BASIS: MoneyBasis = "net_cost";

// Module-level pub-sub so the Settings popup and every card reading the basis
// update together (same pattern as useBudgetAlertSettings).
const listeners = new Set<() => void>();
function subscribe(cb: () => void): () => void {
  listeners.add(cb);
  return () => {
    listeners.delete(cb);
  };
}

function readBasis(): MoneyBasis {
  try {
    return window.localStorage.getItem(KEY) === "cash_flow" ? "cash_flow" : DEFAULT_BASIS;
  } catch {
    return DEFAULT_BASIS;
  }
}

/**
 * The dashboard's counting basis, persisted to localStorage and shared by the
 * Income & Expenses card and the yearly savings figure, so the two always
 * count the same way.
 */
export function useMoneyBasis() {
  const basis = useSyncExternalStore(subscribe, readBasis, () => DEFAULT_BASIS);

  const setBasis = useCallback((value: MoneyBasis) => {
    try {
      window.localStorage.setItem(KEY, value);
    } catch {
      // ignore (private mode / quota)
    }
    listeners.forEach((l) => l());
  }, []);

  return { basis, setBasis };
}
