import { describe, it, expect, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { server } from "../../mocks/server";
import { createMutationCache } from "../../queryInvalidation";
import { AboutPanel } from "./AboutPanel";

/**
 * "Check now" asks the backend to re-probe for an update. It changes no app
 * data, so it must not set off the app-wide refresh every write triggers.
 */
describe("AboutPanel", () => {
  it("re-checks for an update without refreshing the rest of the app", async () => {
    const info = {
      current: "2.2.0",
      latest: "2.3.0",
      is_outdated: true,
      checked_at: "2026-10-26T08:00:00Z",
    };
    server.use(
      http.get("/api/updates/check", () => HttpResponse.json(info)),
      http.post("/api/updates/check", () => HttpResponse.json(info)),
      http.get("/api/version", () =>
        HttpResponse.json({ version: "2.2.0", platform: "linux" }),
      ),
    );
    const client: QueryClient = new QueryClient({
      mutationCache: createMutationCache(() => client, 0),
      defaultOptions: { queries: { retry: false } },
    });
    const invalidate = vi.spyOn(client, "invalidateQueries");
    render(
      <QueryClientProvider client={client}>
        <AboutPanel />
      </QueryClientProvider>,
    );

    fireEvent.click(await screen.findByRole("button", { name: /check now/i }));

    await waitFor(() => expect(client.isMutating()).toBe(0));
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(invalidate).not.toHaveBeenCalled();
  });
});
