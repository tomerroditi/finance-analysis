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

  describe("friendly copy vs technical detail", () => {
    it("leads with an explanation chosen by errorType, keeping the raw text", () => {
      // The two used to be one string, so it had to be either debuggable or
      // readable. Now the headline explains and the provider text backs it up.
      renderWithProviders(
        <ScrapeErrorTooltip message={MESSAGE} errorType="INVALID_PASSWORD" />,
      );

      expect(screen.getByText(/rejected the saved login/i)).toBeInTheDocument();
      expect(screen.getByText(/technical details/i)).toBeInTheDocument();
      expect(screen.getByText(MESSAGE)).toBeInTheDocument();
    });

    it("falls back to generic copy for an unrecognised errorType", () => {
      // A category the backend adds later must not leak a raw i18n key path.
      renderWithProviders(
        <ScrapeErrorTooltip message={MESSAGE} errorType="SOMETHING_NEW" />,
      );

      expect(screen.getByText(/unexpected reason/i)).toBeInTheDocument();
      expect(
        screen.queryByText(/dataSources\.scrapeError/),
      ).not.toBeInTheDocument();
    });

    it("still explains a failure that carries no technical detail", () => {
      renderWithProviders(<ScrapeErrorTooltip errorType="TIMEOUT" />);

      expect(screen.getByText(/took too long to respond/i)).toBeInTheDocument();
      expect(screen.queryByText(/technical details/i)).not.toBeInTheDocument();
    });

    it("shows generic copy for a legacy row that has only a message", () => {
      // Rows recorded before error_type existed keep working.
      renderWithProviders(<ScrapeErrorTooltip message={MESSAGE} />);

      expect(screen.getByText(/unexpected reason/i)).toBeInTheDocument();
      expect(screen.getByText(MESSAGE)).toBeInTheDocument();
    });
  });
});
