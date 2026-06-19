import { describe, it, expect } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { ScrapeErrorTooltip } from "./ScrapeErrorTooltip";

const MESSAGE = "HTTP 503 /v1/otp/prepare — body: prefix blocked";

describe("ScrapeErrorTooltip", () => {
  it("reveals the failure message on tap (no hover needed)", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ScrapeErrorTooltip message={MESSAGE} />);

    const button = screen.getByRole("button", { name: /show error details/i });
    expect(button).toHaveAttribute("aria-expanded", "false");

    await user.click(button);

    expect(button).toHaveAttribute("aria-expanded", "true");
    expect(screen.getByText(MESSAGE)).toBeVisible();
  });

  it("toggles closed on a second tap", async () => {
    const user = userEvent.setup();
    renderWithProviders(<ScrapeErrorTooltip message={MESSAGE} />);

    const button = screen.getByRole("button", { name: /show error details/i });
    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");

    await user.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("always renders the message text in the DOM for hover fallback", () => {
    renderWithProviders(<ScrapeErrorTooltip message={MESSAGE} />);
    expect(screen.getByText(MESSAGE)).toBeInTheDocument();
  });
});
