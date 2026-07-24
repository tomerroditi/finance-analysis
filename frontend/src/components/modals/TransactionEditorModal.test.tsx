import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithProviders } from "../../test-utils";
import { server } from "../../mocks/server";
import { TransactionEditorModal } from "./TransactionEditorModal";

const cashTransaction = {
  unique_id: "12",
  source: "cash_transactions",
  description: "Groceries",
  amount: -150,
  date: "2026-03-15",
  category: "Food",
  tag: "Groceries",
  account_name: "Wallet",
};

function renderEditor() {
  const onSuccess = vi.fn();
  const onClose = vi.fn();
  const utils = renderWithProviders(
    <TransactionEditorModal
      transaction={cashTransaction}
      onSuccess={onSuccess}
      onClose={onClose}
    />,
  );
  const amountInput = screen.getByRole("spinbutton") as HTMLInputElement;
  return { ...utils, amountInput, onSuccess, onClose };
}

describe("TransactionEditorModal amount field", () => {
  let puts: number;

  beforeEach(() => {
    puts = 0;
    server.use(
      http.put("/api/transactions/:id", async () => {
        puts += 1;
        return HttpResponse.json({ status: "ok" });
      }),
    );
  });

  // Regression: `amount: parseFloat(e.target.value)` stored NaN the moment
  // the field was cleared. React rendered "NaN" back into the controlled
  // input and submit serialised `"amount": null`, which the backend rejected
  // with a 422 behind a generic "failed to update" toast naming no field.
  it("renders an empty field, never NaN, when the amount is cleared", () => {
    const { amountInput } = renderEditor();
    expect(amountInput.value).toBe("-150");

    fireEvent.change(amountInput, { target: { value: "" } });
    expect(amountInput.value).toBe("");
    expect(amountInput.value).not.toContain("NaN");
  });

  it("blocks submit with a named error instead of sending a null amount", async () => {
    const { amountInput, onSuccess } = renderEditor();
    fireEvent.change(amountInput, { target: { value: "" } });
    fireEvent.submit(amountInput.closest("form")!);

    await waitFor(() =>
      expect(screen.getByText(/valid amount/i)).toBeInTheDocument(),
    );
    expect(puts).toBe(0);
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("submits normally once a valid amount is entered", async () => {
    const { amountInput, onSuccess } = renderEditor();
    fireEvent.change(amountInput, { target: { value: "" } });
    fireEvent.change(amountInput, { target: { value: "-42.5" } });
    expect(amountInput.value).toBe("-42.5");

    fireEvent.submit(amountInput.closest("form")!);

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(puts).toBe(1);
  });
});
