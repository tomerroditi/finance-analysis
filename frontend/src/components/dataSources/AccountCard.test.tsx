import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountCard } from "./AccountCard";
import type { BankBalance } from "../../services/api";

function balance(overrides: Partial<BankBalance> = {}): BankBalance {
  return {
    id: 1,
    provider: "hapoalim",
    account_name: "Shir",
    balance: 70271.37,
    prior_wealth_amount: 17117.69,
    last_manual_update: null,
    last_scrape_update: "2026-10-10",
    balance_source: "scraped",
    last_drift: 0,
    ...overrides,
  };
}

function renderCard(bal: BankBalance | undefined) {
  return render(
    <AccountCard
      acc={{ service: "banks", provider: "hapoalim", account_name: "Shir" }}
      scraper={undefined}
      lastScrapeDate="2026-10-10"
      balance={bal}
      scrapedToday
      selected={false}
      onToggleSelected={vi.fn()}
      tfaIsPending={false}
      tfaCode=""
      onTfaCodeChange={vi.fn()}
      onSubmitTfa={vi.fn()}
      onResendTfa={vi.fn()}
      resendCooldownRemaining={0}
      resendErrorInfo={undefined}
      onStartScrape={vi.fn()}
      onAbortScrape={vi.fn()}
      onOpenBalanceModal={vi.fn()}
      onView={vi.fn()}
      onEdit={vi.fn()}
      onDelete={vi.fn()}
    />,
  );
}

describe("AccountCard bank balance", () => {
  it("says a scraped balance came from the bank", () => {
    renderCard(balance());

    expect(screen.getByTestId("bank-balance")).toHaveAttribute(
      "title",
      "Reported by the bank at the last sync",
    );
  });

  it("says when a manual balance was typed", () => {
    renderCard(balance({ balance_source: "manual", last_manual_update: "2026-07-10" }));

    expect(screen.getByTestId("bank-balance")).toHaveAttribute(
      "title",
      "Entered by hand on 2026-07-10",
    );
  });

  it("warns when the bank held less than the transactions add up to", () => {
    renderCard(balance({ last_drift: -2333.17 }));

    expect(screen.getByTestId("balance-drift").textContent).toMatch(
      /2,333.*less than the transactions/,
    );
  });

  it("warns when the bank held more", () => {
    renderCard(balance({ last_drift: 120 }));

    expect(screen.getByTestId("balance-drift").textContent).toMatch(/120.*more than/);
  });

  it("stays quiet when the bank and the transactions agree", () => {
    renderCard(balance({ last_drift: 0.4 }));

    expect(screen.queryByTestId("balance-drift")).toBeNull();
  });

  it("never warns over a manual balance", () => {
    renderCard(balance({ balance_source: "manual", last_drift: -500 }));

    expect(screen.queryByTestId("balance-drift")).toBeNull();
  });

  it("keeps the manual entry button for a scraped balance", () => {
    renderCard(balance());

    expect(screen.getByRole("button", { name: "Set Balance" })).toBeEnabled();
  });
});
