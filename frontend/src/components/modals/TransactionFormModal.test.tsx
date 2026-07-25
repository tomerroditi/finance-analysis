import { describe, expect, it, vi, beforeEach } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { renderWithProviders } from "../../test-utils";
import { server } from "../../mocks/server";
import { TransactionFormModal } from "./TransactionFormModal";

describe("TransactionFormModal amount field", () => {
  let posts: number;

  beforeEach(() => {
    posts = 0;
    server.use(
      http.post("/api/transactions/", async () => {
        posts += 1;
        return HttpResponse.json({ status: "ok" });
      }),
    );
  });

  function renderCreate() {
    const onSuccess = vi.fn();
    const utils = renderWithProviders(
      <TransactionFormModal
        isOpen
        service="cash"
        onClose={vi.fn()}
        onSuccess={onSuccess}
      />,
    );
    const amountInput = screen.getByRole("spinbutton") as HTMLInputElement;
    return { ...utils, amountInput, onSuccess };
  }

  // Same regression as TransactionEditorModal: a cleared field became NaN,
  // which serialised to `"amount": null` and came back 422 behind a generic
  // "failed to save" toast.
  it("keeps a cleared amount field empty rather than NaN", () => {
    const { amountInput } = renderCreate();
    fireEvent.change(amountInput, { target: { value: "" } });
    expect(amountInput.value).toBe("");
    expect(amountInput.value).not.toContain("NaN");
  });

  it("blocks submit with a named error instead of posting a null amount", async () => {
    const { amountInput, onSuccess } = renderCreate();
    fireEvent.change(amountInput, { target: { value: "" } });
    fireEvent.submit(amountInput.closest("form")!);

    await waitFor(() =>
      expect(screen.getByText(/valid amount/i)).toBeInTheDocument(),
    );
    expect(posts).toBe(0);
    expect(onSuccess).not.toHaveBeenCalled();
  });

  it("posts a valid amount as a negative expense", async () => {
    const { amountInput, onSuccess } = renderCreate();
    fireEvent.change(amountInput, { target: { value: "42.5" } });
    fireEvent.submit(amountInput.closest("form")!);

    await waitFor(() => expect(onSuccess).toHaveBeenCalled());
    expect(posts).toBe(1);
  });
});
