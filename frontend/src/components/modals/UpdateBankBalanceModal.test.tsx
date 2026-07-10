import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { UpdateBankBalanceModal } from "./UpdateBankBalanceModal";
import { bankBalancesApi } from "../../services/api";
import type * as ApiModule from "../../services/api";

vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    bankBalancesApi: { ...actual.bankBalancesApi, setBalance: vi.fn() },
  };
});

describe("UpdateBankBalanceModal", () => {
  const baseProps = {
    isOpen: true,
    onClose: vi.fn(),
    provider: "hapoalim",
    accountName: "My Checking",
    currentBalance: 1234,
    isScrapedToday: true,
  };

  beforeEach(() => vi.clearAllMocks());

  it("shows the explanation, account name, and an enabled Save when scraped today", () => {
    renderWithProviders(<UpdateBankBalanceModal {...baseProps} />);
    expect(screen.getByText("My Checking")).toBeInTheDocument();
    expect(screen.getByText(/net worth/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Save$/ })).toBeEnabled();
  });

  it("submits provider, account_name, and parsed balance on Save", async () => {
    vi.mocked(bankBalancesApi.setBalance).mockResolvedValue({ data: {} } as never);
    const user = userEvent.setup();
    renderWithProviders(<UpdateBankBalanceModal {...baseProps} />);
    const input = screen.getByRole("spinbutton");
    await user.clear(input);
    await user.type(input, "5000");
    await user.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() =>
      expect(bankBalancesApi.setBalance).toHaveBeenCalledWith({
        provider: "hapoalim",
        account_name: "My Checking",
        balance: 5000,
      }),
    );
  });

  it("disables the input and Save and shows a scrape-first note when not scraped today", () => {
    renderWithProviders(
      <UpdateBankBalanceModal {...baseProps} isScrapedToday={false} />,
    );
    expect(screen.getByRole("spinbutton")).toBeDisabled();
    expect(screen.getByRole("button", { name: /^Save$/ })).toBeDisabled();
    expect(screen.getByText(/then set its balance/i)).toBeInTheDocument();
  });
});
