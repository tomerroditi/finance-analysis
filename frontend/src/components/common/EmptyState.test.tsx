import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Inbox } from "lucide-react";
import { EmptyState } from "./EmptyState";
import { renderWithProviders } from "../../test-utils";

describe("EmptyState", () => {
  it("renders the title and (optional) description", () => {
    renderWithProviders(
      <EmptyState
        icon={Inbox}
        title="No transactions yet"
        description="Connect an account to see your history."
      />,
    );
    expect(screen.getByText("No transactions yet")).toBeInTheDocument();
    expect(
      screen.getByText("Connect an account to see your history."),
    ).toBeInTheDocument();
  });

  it("invokes the primary CTA on click", async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    renderWithProviders(
      <EmptyState
        icon={Inbox}
        title="No transactions yet"
        cta={{ label: "Connect an account", onClick }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Connect an account" }));
    expect(onClick).toHaveBeenCalledTimes(1);
  });

  it("invokes the secondary CTA on click", async () => {
    const user = userEvent.setup();
    const onPrimary = vi.fn();
    const onSecondary = vi.fn();
    renderWithProviders(
      <EmptyState
        icon={Inbox}
        title="No transactions yet"
        cta={{ label: "Connect", onClick: onPrimary }}
        secondary={{ label: "Try the demo", onClick: onSecondary }}
      />,
    );
    await user.click(screen.getByRole("button", { name: "Try the demo" }));
    expect(onSecondary).toHaveBeenCalledTimes(1);
    expect(onPrimary).not.toHaveBeenCalled();
  });

  it("renders the footer slot when provided", () => {
    renderWithProviders(
      <EmptyState
        icon={Inbox}
        title="No transactions yet"
        footer={<span data-testid="custom-footer">Custom footer</span>}
      />,
    );
    expect(screen.getByTestId("custom-footer")).toBeInTheDocument();
  });

  it("hides the action row when no CTAs are provided", () => {
    renderWithProviders(
      <EmptyState icon={Inbox} title="No transactions yet" />,
    );
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("exposes itself as a status region for screen readers", () => {
    renderWithProviders(
      <EmptyState icon={Inbox} title="No transactions yet" />,
    );
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders without an icon when icon prop is omitted", () => {
    renderWithProviders(<EmptyState title="No data" />);
    expect(screen.getByRole("status")).toBeInTheDocument();
    // No SVG icon wrapper present
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("renders step cards with arrows when steps prop is provided", () => {
    renderWithProviders(
      <EmptyState
        title="No data"
        steps={[
          { title: "Connect", description: "Add your accounts" },
          { title: "Scrape", description: "Import transactions" },
          { title: "Analyse", description: "See your picture" },
        ]}
      />,
    );
    expect(screen.getByText("Connect")).toBeInTheDocument();
    expect(screen.getByText("Add your accounts")).toBeInTheDocument();
    expect(screen.getByText("Scrape")).toBeInTheDocument();
    expect(screen.getByText("Analyse")).toBeInTheDocument();
    // Two arrows between three steps
    expect(screen.getAllByText("→")).toHaveLength(2);
  });
});
