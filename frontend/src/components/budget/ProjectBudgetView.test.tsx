import { describe, it, expect, vi, beforeEach } from "vitest";
import { waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { ProjectBudgetView } from "./ProjectBudgetView";
import {
  budgetApi,
  pendingRefundsApi,
  type PendingRefund,
  type ProjectStatus,
} from "../../services/api";
import type * as ApiModule from "../../services/api";

/**
 * Which project the tab opens on when the URL names none.
 *
 * A closed project is finished, not deleted — it keeps its tab and its
 * history. Opening on it (it merely happened to be first in the list) put
 * the user in front of spending they had already settled, with the rest of
 * the page's actions offering to reopen it. The tab now starts on the first
 * project still running, and only falls back to a closed one when there is
 * nothing else to show.
 */
vi.mock("../../services/api", async (importOriginal) => {
  const actual = await importOriginal<typeof ApiModule>();
  return {
    ...actual,
    budgetApi: {
      ...actual.budgetApi,
      getProjectsStatus: vi.fn(),
      getProjectDetails: vi.fn(),
    },
    pendingRefundsApi: {
      ...actual.pendingRefundsApi,
      getAll: vi.fn(),
    },
  };
});

vi.mock("./BudgetNoticeLine", () => ({ BudgetNoticeLine: () => null }));

function renderWithProjects(
  projects: ProjectStatus[],
  initialProject?: string,
) {
  vi.mocked(budgetApi.getProjectsStatus).mockResolvedValue({
    data: projects,
  } as Awaited<ReturnType<typeof budgetApi.getProjectsStatus>>);
  return renderWithProviders(
    <ProjectBudgetView tabs={null} initialProject={initialProject} />,
  );
}

/** The project the view asked the backend for — i.e. the one it selected. */
async function selectedProject() {
  await waitFor(() =>
    expect(budgetApi.getProjectDetails).toHaveBeenCalled(),
  );
  return vi.mocked(budgetApi.getProjectDetails).mock.calls[0][0];
}

describe("ProjectBudgetView auto-selection", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(pendingRefundsApi.getAll).mockResolvedValue({
      data: [] as PendingRefund[],
    } as Awaited<ReturnType<typeof pendingRefundsApi.getAll>>);
    vi.mocked(budgetApi.getProjectDetails).mockResolvedValue({
      data: { name: "", rules: [], total_spent: 0 },
    } as Awaited<ReturnType<typeof budgetApi.getProjectDetails>>);
  });

  it("skips a closed project for the first one still running", async () => {
    renderWithProjects([
      { name: "Home Renovation", closed: true },
      { name: "Our Wedding", closed: false },
    ]);

    expect(await selectedProject()).toBe("Our Wedding");
  });

  it("keeps the first project when nothing is closed", async () => {
    renderWithProjects([
      { name: "Home Renovation", closed: false },
      { name: "Our Wedding", closed: false },
    ]);

    expect(await selectedProject()).toBe("Home Renovation");
  });

  it("falls back to a closed project when every project is closed", async () => {
    renderWithProjects([
      { name: "Home Renovation", closed: true },
      { name: "Our Wedding", closed: true },
    ]);

    // Better a settled project with its history than an empty tab.
    expect(await selectedProject()).toBe("Home Renovation");
  });

  it("honours a project named by the link that got here, closed or not", async () => {
    renderWithProjects(
      [
        { name: "Home Renovation", closed: true },
        { name: "Our Wedding", closed: false },
      ],
      "Home Renovation",
    );

    expect(await selectedProject()).toBe("Home Renovation");
  });
});
