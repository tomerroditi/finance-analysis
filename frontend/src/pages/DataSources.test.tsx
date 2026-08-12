import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "../test-utils";
import { server } from "../mocks/server";
import { DataSources } from "./DataSources";

/** Records every DELETE /api/credentials/... URL the page issues. */
function captureCredentialDeletes(transactionsDeleted = 0) {
  const requested: URL[] = [];
  server.use(
    http.delete("/api/credentials/:service/:provider/:account", ({ request }) => {
      requested.push(new URL(request.url));
      return HttpResponse.json({
        status: "success",
        transactions_deleted: transactionsDeleted,
      });
    }),
  );
  return requested;
}

/** Opens the disconnect modal for the first connected account. */
async function openDisconnectModal(user: ReturnType<typeof userEvent.setup>) {
  await waitFor(() => {
    expect(screen.getByText(/Main Account/i)).toBeInTheDocument();
  });
  const disconnectButtons = screen.getAllByRole("button", {
    name: /disconnect account/i,
  });
  await user.click(disconnectButtons[0]);
  return screen.getByRole("dialog");
}

describe("DataSources", () => {
  describe("connected accounts", () => {
    it("displays saved credentials from the API", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Main Account/i)).toBeInTheDocument();
      });
    });

    it("shows provider names for connected accounts", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Hapoalim/i)).toBeInTheDocument();
      });
    });
  });

  describe("bank balances", () => {
    it("displays bank balance information", async () => {
      renderWithProviders(<DataSources />);
      await waitFor(() => {
        expect(screen.getByText(/Main Account/i)).toBeInTheDocument();
      });
    });
  });

  describe("disconnect account data choice", () => {
    it("preselects keeping data and never preselects the destructive option", async () => {
      const user = userEvent.setup();
      renderWithProviders(<DataSources />);
      await openDisconnectModal(user);

      expect(screen.getByRole("radio", { name: /keep my data/i })).toBeChecked();
      expect(
        screen.getByRole("radio", { name: /delete everything/i }),
      ).not.toBeChecked();
    });

    it("sends delete_data=false when the default choice is confirmed", async () => {
      const user = userEvent.setup();
      const requested = captureCredentialDeletes();
      renderWithProviders(<DataSources />);
      await openDisconnectModal(user);

      await user.click(
        screen.getByRole("button", { name: /disconnect, keep data/i }),
      );

      await waitFor(() => expect(requested).toHaveLength(1));
      expect(requested[0].pathname).toBe(
        "/api/credentials/banks/hapoalim/Main%20Account",
      );
      expect(requested[0].searchParams.get("delete_data")).toBe("false");
    });

    it("sends delete_data=true when the destructive choice is selected", async () => {
      const user = userEvent.setup();
      const requested = captureCredentialDeletes(7);
      renderWithProviders(<DataSources />);
      await openDisconnectModal(user);

      await user.click(screen.getByRole("radio", { name: /delete everything/i }));
      await user.click(
        screen.getByRole("button", { name: /disconnect and delete data/i }),
      );

      await waitFor(() => expect(requested).toHaveLength(1));
      expect(requested[0].searchParams.get("delete_data")).toBe("true");
    });

    it("reports how many transactions were deleted", async () => {
      const user = userEvent.setup();
      captureCredentialDeletes(7);
      renderWithProviders(<DataSources />);
      await openDisconnectModal(user);

      await user.click(screen.getByRole("radio", { name: /delete everything/i }));
      await user.click(
        screen.getByRole("button", { name: /disconnect and delete data/i }),
      );

      await waitFor(() => {
        expect(screen.getByText(/7 transactions were deleted/i)).toBeInTheDocument();
      });
    });

    it("issues no request when the modal is cancelled", async () => {
      const user = userEvent.setup();
      const requested = captureCredentialDeletes();
      renderWithProviders(<DataSources />);
      await openDisconnectModal(user);

      await user.click(screen.getByRole("button", { name: /^cancel$/i }));

      await waitFor(() =>
        expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
      );
      expect(requested).toHaveLength(0);
    });
  });
  describe("Scrape All eligibility", () => {
    /**
     * Stub last-scrapes + start, and return the accounts each Scrape All
     * dispatch tried to launch. `hapoalim/Main Account` reports a scrape
     * timestamped now; `max/Max Card` was last synced days ago.
     */
    function stubScrapeAll() {
      const started: string[] = [];
      server.use(
        http.get("/api/scraping/last-scrapes", () =>
          HttpResponse.json([
            {
              service: "banks",
              provider: "hapoalim",
              account_name: "Main Account",
              last_scrape_date: new Date().toISOString(),
            },
            {
              service: "credit_cards",
              provider: "max",
              account_name: "Max Card",
              last_scrape_date: "2026-01-02T08:00:00",
            },
          ]),
        ),
        http.post("/api/scraping/start", async ({ request }) => {
          const body = (await request.json()) as { account: string };
          started.push(body.account);
          return HttpResponse.json(started.length);
        }),
      );
      return started;
    }

    /** The Scrape All button, located by label in either of its two states. */
    const scrapeAllButton = () =>
      screen.getByRole("button", { name: /scrape all/i });

    it("skips accounts already synced today", async () => {
      // A same-day re-run re-fetches a window the account already has, and on
      // a 2FA provider it costs the user another SMS.
      const user = userEvent.setup();
      const started = stubScrapeAll();
      renderWithProviders(<DataSources />);

      await waitFor(() => {
        expect(screen.getByText(/Max Card/i)).toBeInTheDocument();
      });
      await waitFor(() => expect(scrapeAllButton()).toBeEnabled());
      await user.click(scrapeAllButton());

      await waitFor(() => expect(started).toEqual(["Max Card"]));
      expect(started).not.toContain("Main Account");
    });

    it("disables Scrape All, with an explanation, once nothing is eligible", async () => {
      const user = userEvent.setup();
      stubScrapeAll();
      renderWithProviders(<DataSources />);

      await waitFor(() => {
        expect(screen.getByText(/Max Card/i)).toBeInTheDocument();
      });
      await waitFor(() => expect(scrapeAllButton()).toBeEnabled());
      await user.click(scrapeAllButton());

      // "Main Account" was synced today and "Max Card" is now scraping, so the
      // bulk action has nothing left to do — and says why, rather than looking
      // broken. A single source is still re-scrapable from its own card.
      await waitFor(() => expect(scrapeAllButton()).toBeDisabled());
      expect(scrapeAllButton()).toHaveAttribute(
        "title",
        expect.stringContaining("synced today"),
      );
    });
  });
});
