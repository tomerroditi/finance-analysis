import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import type { OnboardingStatus } from "../services/api";
import { OnboardingGate } from "./OnboardingGate";

const useOnboardingStatusMock = vi.fn();

vi.mock("../hooks/useOnboardingStatus", () => ({
  useOnboardingStatus: () => useOnboardingStatusMock(),
  ONBOARDING_STATUS_KEY: ["onboardingStatus"],
}));

const ONBOARDING_DISMISSED_KEY = "onboardingDismissedAt";

function status(overrides: Partial<OnboardingStatus> = {}): OnboardingStatus {
  return {
    has_credentials: false,
    has_transactions: false,
    has_budgets: false,
    has_investments: false,
    is_first_run: false,
    ...overrides,
  };
}

function renderGate({
  pathname = "/",
  data,
  isLoading = false,
}: {
  pathname?: string;
  data: OnboardingStatus | undefined;
  isLoading?: boolean;
}) {
  useOnboardingStatusMock.mockReturnValue({ data, isLoading });
  return render(
    <MemoryRouter initialEntries={[pathname]}>
      <Routes>
        <Route element={<OnboardingGate />}>
          <Route path="/" element={<div data-testid="dashboard">DASHBOARD</div>} />
          <Route
            path="/transactions"
            element={<div data-testid="transactions">TX</div>}
          />
        </Route>
        <Route
          path="/onboarding"
          element={<div data-testid="wizard">WIZARD</div>}
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("OnboardingGate", () => {
  beforeEach(() => {
    useOnboardingStatusMock.mockReset();
    sessionStorage.clear();
  });

  it("renders the dashboard when the user is not in a first-run state", () => {
    renderGate({ data: status({ is_first_run: false }) });
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  });

  it("redirects from / to /onboarding when is_first_run is true", async () => {
    renderGate({ data: status({ is_first_run: true }) });
    await waitFor(() => {
      expect(screen.getByTestId("wizard")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("dashboard")).not.toBeInTheDocument();
  });

  it("does NOT redirect when the user is on a non-root path", async () => {
    renderGate({
      pathname: "/transactions",
      data: status({ is_first_run: true }),
    });
    expect(screen.getByTestId("transactions")).toBeInTheDocument();
    // Wait a tick to ensure no late redirect fires.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  });

  it("does NOT redirect while the status query is still loading", async () => {
    renderGate({ data: undefined, isLoading: true });
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  });

  it("stamps sessionStorage with a dismissal timestamp on redirect", async () => {
    renderGate({ data: status({ is_first_run: true }) });
    await waitFor(() => {
      expect(screen.getByTestId("wizard")).toBeInTheDocument();
    });
    const stamp = sessionStorage.getItem(ONBOARDING_DISMISSED_KEY);
    expect(stamp).not.toBeNull();
    expect(Number(stamp)).toBeGreaterThan(0);
  });

  it("respects an existing sessionStorage dismissal — no second redirect", async () => {
    sessionStorage.setItem(ONBOARDING_DISMISSED_KEY, "1");
    renderGate({ data: status({ is_first_run: true }) });
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  });

  it("renders the dashboard when the API hasn't responded yet (data undefined, not loading)", async () => {
    renderGate({ data: undefined, isLoading: false });
    expect(screen.getByTestId("dashboard")).toBeInTheDocument();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByTestId("wizard")).not.toBeInTheDocument();
  });
});
