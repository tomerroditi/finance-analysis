import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";

import { ColumnMappingWizard } from "./ColumnMappingWizard";

// Stub out the preview API call so the test doesn't hit the network.
vi.mock("../../services/api", () => ({
  importedAccountsApi: {
    preview: vi.fn().mockResolvedValue({
      data: {
        rows: [
          { date: "2026-03-01", description: "Coffee", amount: -12.5 },
        ],
        dropped_invalid: 0,
        raw_headers: ["date", "description", "amount"],
      },
    }),
    templateUrl: () => "/api/imported-accounts/template",
  },
}));

const FILE = new File(
  ["date,description,amount\n2026-03-01,Coffee,-12.5\n"],
  "test.csv",
  { type: "text/csv" },
);

describe("ColumnMappingWizard", () => {
  it("blocks save until required fields are mapped", async () => {
    const onSave = vi.fn();
    render(<ColumnMappingWizard file={FILE} initialMapping={null} onSave={onSave} />);
    const saveBtn = await screen.findByRole("button", { name: /save/i });
    expect(saveBtn).toBeDisabled();
  });

  it("emits a complete ColumnMapping when the user fills in required fields", async () => {
    const onSave = vi.fn();
    render(<ColumnMappingWizard file={FILE} initialMapping={null} onSave={onSave} />);

    // Wait for the headers to load — the date select gets a "date" option
    // once the preview API resolves.
    await waitFor(() => {
      const dateSelect = screen.getByLabelText(/date column/i) as HTMLSelectElement;
      expect(
        Array.from(dateSelect.options).some((o) => o.value === "date"),
      ).toBe(true);
    });

    fireEvent.change(screen.getByLabelText(/date column/i), {
      target: { value: "date" },
    });
    fireEvent.change(screen.getByLabelText(/description column/i), {
      target: { value: "description" },
    });
    fireEvent.change(screen.getByLabelText(/^amount column/i), {
      target: { value: "amount" },
    });

    const saveBtn = await screen.findByRole("button", { name: /save/i });
    await waitFor(() => expect(saveBtn).not.toBeDisabled());
    fireEvent.click(saveBtn);
    expect(onSave).toHaveBeenCalledTimes(1);
    const mapping = onSave.mock.calls[0][0];
    expect(mapping.date.column).toBe("date");
    expect(mapping.amount.mode).toBe("single");
    expect(mapping.amount.column).toBe("amount");
  });
});
