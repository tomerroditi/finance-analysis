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
});
