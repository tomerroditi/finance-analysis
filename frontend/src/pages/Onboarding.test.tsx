import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type * as ReactRouterDom from "react-router-dom";
import { Onboarding } from "./Onboarding";
import { renderWithProviders } from "../test-utils";

const navigateMock = vi.fn();
const toggleDemoModeMock = vi.fn(async () => {});

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
  });

  it("starts on the language step", () => {
    renderWithProviders(<Onboarding />);
    expect(
      screen.getByRole("heading", { name: /welcome|ברוך/i, level: 1 }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /English/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /עברית/ })).toBeInTheDocument();
  });

  it("advances from language to path step on selection", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Onboarding />);
    await user.click(screen.getByRole("button", { name: /English/ }));
    expect(
      await screen.findByRole("heading", { name: /pick how to start|איך מתחילים/i }),
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

  it("the skip link routes back to the dashboard at any step", async () => {
    const user = userEvent.setup();
    renderWithProviders(<Onboarding />);
    const skip = screen.getByRole("button", { name: /Skip for now/i });
    await user.click(skip);
    expect(navigateMock).toHaveBeenCalledWith("/");
  });
});
