import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { DemoModeConfirmPopover } from "./DemoModeConfirmPopover";
import { renderWithProviders } from "../../test-utils";

describe("DemoModeConfirmPopover", () => {
  it("renders the confirmation description and both action buttons", () => {
    renderWithProviders(<DemoModeConfirmPopover onClose={vi.fn()} />);
    expect(screen.getByText(/sample data/i)).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /enable demo mode/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /cancel/i }),
    ).toBeInTheDocument();
  });

  it("calls onClose when Cancel is clicked", async () => {
    const user = userEvent.setup();
    const onClose = vi.fn();
    renderWithProviders(<DemoModeConfirmPopover onClose={onClose} />);
    await user.click(screen.getByRole("button", { name: /cancel/i }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
