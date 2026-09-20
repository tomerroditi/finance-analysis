import { describe, it, expect, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test-utils";
import { MultiSelect } from "./MultiSelect";

/**
 * The select-all row exists because a budget envelope usually covers its
 * whole category: ticking seven wedding tags one by one is the common path,
 * not an edge case. It is opt-in (`showSelectAll`) — in a filter, selecting
 * every option means the same thing as selecting none, so the control would
 * be a button that changes nothing.
 */
const TAGS = ["Venue", "Catering", "Photography", "Rings"];

function render(props: Partial<React.ComponentProps<typeof MultiSelect>> = {}) {
  const onChange = vi.fn();
  renderWithProviders(
    <MultiSelect
      options={TAGS}
      selected={[]}
      onChange={onChange}
      showSelectAll
      {...props}
    />,
  );
  return { onChange };
}

/** Open the dropdown — it renders into a portal, not inside the trigger. */
async function openDropdown() {
  await userEvent.click(screen.getAllByRole("button")[0]);
  return screen.getByRole("listbox").parentElement as HTMLElement;
}

describe("MultiSelect select-all", () => {
  it("is absent unless the caller asks for it", async () => {
    render({ showSelectAll: false });
    await openDropdown();

    expect(screen.queryByTestId("multiselect-select-all")).toBeNull();
  });

  it("selects every option in one click", async () => {
    const { onChange } = render();
    await openDropdown();

    await userEvent.click(screen.getByTestId("multiselect-select-all"));

    expect(onChange).toHaveBeenCalledWith(TAGS);
  });

  it("keeps options already selected rather than duplicating them", async () => {
    const { onChange } = render({ selected: ["Venue"] });
    await openDropdown();

    await userEvent.click(screen.getByTestId("multiselect-select-all"));

    expect(onChange).toHaveBeenCalledWith([
      "Venue",
      "Catering",
      "Photography",
      "Rings",
    ]);
  });

  it("turns into the undo once everything is selected", async () => {
    const { onChange } = render({ selected: TAGS });
    await openDropdown();

    const row = screen.getByTestId("multiselect-select-all");
    expect(row.textContent).toMatch(/deselect all/i);

    await userEvent.click(row);
    expect(onChange).toHaveBeenCalledWith([]);
  });

  it("covers only what the search box is showing", async () => {
    const { onChange } = render();
    const dropdown = await openDropdown();

    await userEvent.type(
      within(dropdown).getByPlaceholderText(/search/i),
      "ing",
    );
    await userEvent.click(screen.getByTestId("multiselect-select-all"));

    // "Catering" and "Rings" match; the other two are off screen and must
    // not be swept in by a control the user aimed at the matches.
    expect(onChange).toHaveBeenCalledWith(["Catering", "Rings"]);
  });

  it("leaves hidden selections alone when deselecting a filtered set", async () => {
    const { onChange } = render({ selected: ["Venue", "Rings"] });
    const dropdown = await openDropdown();

    await userEvent.type(
      within(dropdown).getByPlaceholderText(/search/i),
      "Rings",
    );
    await userEvent.click(screen.getByTestId("multiselect-select-all"));

    expect(onChange).toHaveBeenCalledWith(["Venue"]);
  });
});
