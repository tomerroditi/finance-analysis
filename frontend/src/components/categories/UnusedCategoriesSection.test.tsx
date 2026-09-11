import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../../test-utils";
import { UnusedCategoriesSection } from "./UnusedCategoriesSection";

const usage = {
  Wedding: { last_used: "2025-01-20", unused: true },
  Renovation: { last_used: null, unused: true },
};

describe("UnusedCategoriesSection", () => {
  it("renders nothing when there are no unused categories", () => {
    const { container } = renderWithProviders(
      <UnusedCategoriesSection
        entries={[]}
        icons={{}}
        usage={{}}
        expanded={false}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("hides the grid when collapsed", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={false}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
    expect(screen.queryByTestId("unused-categories-grid")).not.toBeInTheDocument();
  });

  it("shows the cards when expanded", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    expect(screen.getByTestId("category-card-Wedding")).toBeInTheDocument();
  });

  it("calls onToggle when the disclosure is clicked", () => {
    const onToggle = vi.fn();
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={false}
        onToggle={onToggle}
        onSelect={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("unused-categories-toggle"));
    expect(onToggle).toHaveBeenCalledOnce();
  });

  it("labels a never-used category distinctly from a stale one", () => {
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[
          ["Wedding", ["Venue"]],
          ["Renovation", ["Labor"]],
        ]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={() => {}}
      />,
    );
    const wedding = screen.getByTestId("category-card-Wedding");
    const renovation = screen.getByTestId("category-card-Renovation");
    expect(wedding.textContent).not.toEqual(renovation.textContent);
    expect(renovation.textContent).toMatch(/neverUsed|never used/i);
  });

  it("calls onSelect with the category when a card is clicked", () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <UnusedCategoriesSection
        entries={[["Wedding", ["Venue"]]]}
        icons={{}}
        usage={usage}
        expanded={true}
        onToggle={() => {}}
        onSelect={onSelect}
      />,
    );
    fireEvent.click(screen.getByTestId("category-card-Wedding"));
    expect(onSelect).toHaveBeenCalledWith("Wedding");
  });
});
