import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterDom from "react-router-dom";
import i18n from "../i18n";
import { Onboarding } from "./Onboarding";
import { renderWithProviders } from "../test-utils";

const navigateMock = vi.fn();

// Indirection so individual tests can override the toggle implementation —
// e.g. to stall the promise and verify the busy/disabled state mid-flight.
let toggleDemoModeImpl: (enabled: boolean) => Promise<void> = async () => {};
const toggleDemoModeMock = vi.fn(async (enabled: boolean) =>
  toggleDemoModeImpl(enabled),
);

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof ReactRouterDom>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => navigateMock,
  };
});

vi.mock("../context/DemoModeContext", () => ({
  DemoModeProvider: ({ children }: { children: React.ReactNode }) => children,
  useDemoMode: () => ({
    isDemoMode: false,
    toggleDemoMode: toggleDemoModeMock,
    isLoading: false,
  }),
}));

describe("Onboarding wizard", () => {
  beforeEach(() => {
    navigateMock.mockClear();
    toggleDemoModeMock.mockClear();
    toggleDemoModeImpl = async () => {};
    // Each test starts in English regardless of what the previous one
    // switched to — the Hebrew RTL test in particular leaks language
    // state into the JSDOM document root.
    i18n.changeLanguage("en");
    document.documentElement.dir = "ltr";
  });

  describe("rendering & navigation", () => {
    it("starts on the language step", () => {
      renderWithProviders(<Onboarding />);
      expect(
        screen.getByRole("heading", { name: /welcome|ברוך/i, level: 1 }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /English/ }),
      ).toBeInTheDocument();
      expect(screen.getByRole("button", { name: /עברית/ })).toBeInTheDocument();
    });

    it("advances from language to path step on selection", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      expect(
        await screen.findByRole("heading", {
          name: /pick how to start|איך מתחילים/i,
        }),
      ).toBeInTheDocument();
    });

    it("real-data path lands on the done step and finishes to /data-sources", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Use my real data/i }),
      );
      expect(toggleDemoModeMock).not.toHaveBeenCalled();
      const finish = await screen.findByRole("button", {
        name: /Go to Data Sources/i,
      });
      await user.click(finish);
      expect(navigateMock).toHaveBeenCalledWith("/data-sources");
    });

    it("demo path flips Demo Mode on and finishes to dashboard", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Explore with demo/i }),
      );
      await waitFor(() => {
        expect(toggleDemoModeMock).toHaveBeenCalledWith(true);
      });
      const finish = await screen.findByRole("button", {
        name: /Go to dashboard/i,
      });
      await user.click(finish);
      expect(navigateMock).toHaveBeenCalledWith("/");
    });
  });

  describe("step indicator", () => {
    it("starts at step 1 of 3", () => {
      renderWithProviders(<Onboarding />);
      const progress = screen.getByRole("progressbar");
      expect(progress).toHaveAttribute("aria-valuenow", "1");
      expect(progress).toHaveAttribute("aria-valuemax", "3");
      expect(progress).toHaveAttribute("aria-valuemin", "1");
    });

    it("advances to step 2 after picking a language", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await waitFor(() => {
        expect(screen.getByRole("progressbar")).toHaveAttribute(
          "aria-valuenow",
          "2",
        );
      });
    });

    it("reaches step 3 at the done screen", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Use my real data/i }),
      );
      await waitFor(() => {
        expect(screen.getByRole("progressbar")).toHaveAttribute(
          "aria-valuenow",
          "3",
        );
      });
    });
  });

  describe("path step", () => {
    it("disables both options while the demo toggle is in flight", async () => {
      let resolveToggle!: () => void;
      toggleDemoModeImpl = () =>
        new Promise<void>((resolve) => {
          resolveToggle = resolve;
        });
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Explore with demo/i }),
      );
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Use my real data/i }),
        ).toBeDisabled();
      });
      expect(
        screen.getByRole("button", { name: /Explore with demo/i }),
      ).toBeDisabled();

      // Resolving the toggle should unstick the wizard and advance us
      // to the done step.
      resolveToggle();
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /Go to dashboard/i }),
        ).toBeInTheDocument();
      });
    });
  });

  describe("done step copy", () => {
    it("shows the real-path-specific finish CTA and description", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Use my real data/i }),
      );
      expect(
        await screen.findByRole("button", { name: /Go to Data Sources/i }),
      ).toBeInTheDocument();
      // The real-path description mentions connecting an account; the
      // demo one mentions Demo Mode being on. Pick fragments unique to
      // each so we don't false-match the button label.
      expect(
        screen.getByText(/connect your first account/i),
      ).toBeInTheDocument();
      expect(screen.queryByText(/Demo Mode is on/i)).not.toBeInTheDocument();
    });

    it("shows the demo-path-specific finish CTA and description", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Explore with demo/i }),
      );
      expect(
        await screen.findByRole("button", { name: /Go to dashboard/i }),
      ).toBeInTheDocument();
      expect(screen.getByText(/Demo Mode is on/i)).toBeInTheDocument();
      expect(
        screen.queryByRole("button", { name: /Go to Data Sources/i }),
      ).not.toBeInTheDocument();
    });
  });

  describe("skip", () => {
    it("is visible on the language step and routes to the dashboard", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /Skip for now/i }));
      expect(navigateMock).toHaveBeenCalledWith("/");
    });

    it("remains visible on the path step", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await screen.findByRole("button", { name: /Use my real data/i });
      expect(
        screen.getByRole("button", { name: /Skip for now/i }),
      ).toBeInTheDocument();
    });

    it("remains visible on the done step", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await user.click(
        await screen.findByRole("button", { name: /Use my real data/i }),
      );
      await screen.findByRole("button", { name: /Go to Data Sources/i });
      expect(
        screen.getByRole("button", { name: /Skip for now/i }),
      ).toBeInTheDocument();
    });
  });

  describe("language switching", () => {
    it("Hebrew language pick sets document direction to RTL", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /עברית/ }));
      await waitFor(() => {
        expect(document.documentElement.dir).toBe("rtl");
      });
      expect(i18n.language).toMatch(/^he/);
    });

    it("English language pick keeps document direction as LTR", async () => {
      const user = userEvent.setup();
      // Start in Hebrew so we can prove the English pick reverses it.
      i18n.changeLanguage("he");
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /English/ }));
      await waitFor(() => {
        expect(document.documentElement.dir).toBe("ltr");
      });
      expect(i18n.language).toMatch(/^en/);
    });

    it("Hebrew → real path → Done step renders the Hebrew finish CTA", async () => {
      const user = userEvent.setup();
      renderWithProviders(<Onboarding />);
      await user.click(screen.getByRole("button", { name: /עברית/ }));
      await user.click(
        await screen.findByRole("button", { name: /להשתמש בנתונים אמיתיים/ }),
      );
      expect(
        await screen.findByRole("button", { name: /מעבר למקורות נתונים/ }),
      ).toBeInTheDocument();
    });
  });
});
