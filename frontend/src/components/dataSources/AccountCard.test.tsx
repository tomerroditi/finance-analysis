import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { AccountCard } from "./AccountCard";
import type { BankBalance, CardBilling } from "../../services/api";

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

function renderCard(bal: BankBalance | undefined, cards?: CardBilling[]) {
  return render(
    <AccountCard
      acc={
        cards
          ? { service: "credit_cards", provider: "isracard", account_name: "Tomer" }
          : { service: "banks", provider: "hapoalim", account_name: "Shir" }
      }
      scraper={undefined}
      lastScrapeDate="2026-10-10"
      balance={bal}
      cardBilling={
        cards ? { provider: "isracard", account_name: "Tomer", cards } : undefined
      }
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

function card(overrides: Partial<CardBilling> = {}): CardBilling {
  return {
    account_number: "3040",
    billing_day: 2,
    billing_day_source: "reported",
    next_billing_date: "2026-11-02",
    changes: [{ day: 2, from: "2026-06", to: "2026-10" }],
    paid_from: { provider: "onezero", account_name: "Tomer" },
    ...overrides,
  };
}

describe("AccountCard card billing", () => {
  it("shows each card's billing day, next bill and paying account", () => {
    renderCard(undefined, [card()]);

    const row = screen.getByTestId("card-billing-row");
    expect(row.textContent).toMatch(/3040.*Billing day: 2.*Next bill.*Paid from One Zero · Tomer/);
  });

  it("marks a day it only estimated, and says how", () => {
    renderCard(undefined, [card({ billing_day: 10, billing_day_source: "default", changes: [], paid_from: null })]);

    const day = screen.getByTestId("card-billing-day");
    expect(day.textContent).toContain("~10");
    expect(day).toHaveAttribute("title", expect.stringMatching(/10th is assumed/));
    expect(screen.getByTestId("card-paid-from").textContent).toBe("Paying account not found");
  });

  it("flags a billing day that changed and lists the earlier ones", () => {
    renderCard(undefined, [
      card({
        changes: [
          { day: 10, from: "2025-01", to: "2026-03" },
          { day: 2, from: "2026-04", to: "2026-10" },
        ],
      }),
    ]);

    expect(screen.getByTestId("card-billing-changed")).toBeInTheDocument();
    expect(screen.getByTestId("card-billing-day").getAttribute("title")).toMatch(
      /Day 10: .*\nDay 2: /,
    );
  });

  it("shows nothing for a bank account", () => {
    renderCard(balance());

    expect(screen.queryByTestId("card-billing")).toBeNull();
  });
});
