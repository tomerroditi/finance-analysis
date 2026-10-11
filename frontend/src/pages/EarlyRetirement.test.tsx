import { describe, it, expect } from "vitest";
import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "../test-utils";
import { server } from "../mocks/server";
import { mockFireProjection } from "../mocks/handlers";
import { EarlyRetirement } from "./EarlyRetirement";

async function renderPage() {
  renderWithProviders(<EarlyRetirement />);
  await screen.findByTestId("fire-row-portfolio-1");
}

function cashInput() {
  const section = screen.getByTestId("fire-section-cash");
  return within(section).getAllByRole("spinbutton")[1] as HTMLInputElement;
}

describe("EarlyRetirement", () => {
  it("fills the form from the plan and shows the saved projection", async () => {
    await renderPage();
    const row = screen.getByTestId("fire-row-portfolio-1");
    expect(within(row).getByText("Index fund", { selector: "span" })).toBeInTheDocument();
    expect(cashInput().value).toBe("50000");
    expect(screen.getByTestId("fire-linked-balance")).toBeInTheDocument();
    expect(await screen.findByTestId("fire-verdict")).toHaveTextContent("2042");
  });

  it("unlinks a field the user types over, and relinks it on request", async () => {
    await renderPage();
    fireEvent.change(cashInput(), { target: { value: "1234" } });
    expect(screen.queryByTestId("fire-linked-balance")).not.toBeInTheDocument();
    expect(screen.getByTestId("fire-plan-unsaved")).toBeInTheDocument();

    fireEvent.click(screen.getByTestId("fire-relink-balance"));
    expect(cashInput().value).toBe("50000");
    expect(screen.getByTestId("fire-linked-balance")).toBeInTheDocument();
  });

  it("sync adds the tracked accounts the plan does not hold yet", async () => {
    await renderPage();
    expect(screen.queryByTestId("fire-row-portfolio-2")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("fire-plan-sync"));
    const added = await screen.findByTestId("fire-row-portfolio-2");
    expect(within(added).getByText("Bonds", { selector: "span" })).toBeInTheDocument();
  });

  it("saves the fields with what is still linked", async () => {
    let body: { fields: Record<string, string>; linked: string[] } | undefined;
    server.use(
      http.put("/api/fire/plan", async ({ request }) => {
        body = (await request.json()) as typeof body;
        return HttpResponse.json({ saved: true, fields: body!.fields, linked: body!.linked,
          tracked: { scalars: {}, rows: {} } });
      }),
    );
    await renderPage();
    fireEvent.click(screen.getByTestId("fire-plan-save"));
    await waitFor(() => expect(body).toBeDefined());
    expect(body!.fields.portfolioSource1).toBe("investment:1");
    expect(body!.linked).toEqual(["balance"]);
  });

  it("asks for setup while the plan has no date of birth", async () => {
    server.use(
      http.get("/api/fire/plan/projection", () =>
        HttpResponse.json({ ...mockFireProjection, status: "needs_setup", months: [] }),
      ),
    );
    await renderPage();
    expect(await screen.findByTestId("fire-needs-setup")).toBeInTheDocument();
  });
});
