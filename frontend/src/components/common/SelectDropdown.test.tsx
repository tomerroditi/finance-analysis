import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SelectDropdown } from "./SelectDropdown";
import { renderWithProviders } from "../../test-utils";

const defaultOptions = [
  { label: "Food", value: "food" },
  { label: "Transport", value: "transport" },
  { label: "Salary", value: "salary" },
];

function renderDropdown(overrides: Partial<Parameters<typeof SelectDropdown>[0]> = {}) {
  const onChange = vi.fn();
  const props = {
    options: defaultOptions,
    value: "",
    onChange,
    ...overrides,
  };
  const result = renderWithProviders(<SelectDropdown {...props} />);
  return { ...result, onChange };
}

describe("SelectDropdown", () => {
  describe("rendering", () => {
    it("shows placeholder when no value selected", () => {
      renderDropdown({ placeholder: "Pick one" });
      expect(screen.getByRole("button")).toHaveTextContent("Pick one");
    });

    it("shows default placeholder", () => {
      renderDropdown();
      expect(screen.getByRole("button")).toHaveTextContent("Select...");
    });

    it("shows selected label when value matches", () => {
      renderDropdown({ value: "food" });
      expect(screen.getByRole("button")).toHaveTextContent("Food");
    });
  });

  describe("opening/closing", () => {
    it("opens dropdown on click", async () => {
      const user = userEvent.setup();
      renderDropdown();
      await user.click(screen.getByRole("button"));
      expect(screen.getByText("Food")).toBeInTheDocument();
      expect(screen.getByText("Transport")).toBeInTheDocument();
      expect(screen.getByText("Salary")).toBeInTheDocument();
    });

    it("does not open when disabled", async () => {
      const user = userEvent.setup();
      renderDropdown({ disabled: true });
      await user.click(screen.getByRole("button"));
      // Options should not appear (they are rendered via portal)
      expect(screen.queryAllByText("Food")).toHaveLength(0);
    });
  });

  describe("selection", () => {
    it("calls onChange when option is clicked", async () => {
      const user = userEvent.setup();
      const { onChange } = renderDropdown();
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByText("Transport"));
      expect(onChange).toHaveBeenCalledWith("transport");
    });
  });

  describe("search (when > 5 options)", () => {
    const manyOptions = [
      { label: "Food", value: "food" },
      { label: "Transport", value: "transport" },
      { label: "Salary", value: "salary" },
      { label: "Health", value: "health" },
      { label: "Entertainment", value: "entertainment" },
      { label: "Education", value: "education" },
    ];

    it("shows search input for > 5 options", async () => {
      const user = userEvent.setup();
      renderDropdown({ options: manyOptions });
      await user.click(screen.getByRole("button"));
      expect(screen.getByPlaceholderText("Search...")).toBeInTheDocument();
    });

    it("filters options by search text", async () => {
      const user = userEvent.setup();
      renderDropdown({ options: manyOptions });
      await user.click(screen.getByRole("button"));
      await user.type(screen.getByPlaceholderText("Search..."), "edu");
      expect(screen.getByText("Education")).toBeInTheDocument();
      expect(screen.queryByText("Food")).not.toBeInTheDocument();
    });

    it("shows no matches message when search has no results", async () => {
      const user = userEvent.setup();
      renderDropdown({ options: manyOptions });
      await user.click(screen.getByRole("button"));
      await user.type(screen.getByPlaceholderText("Search..."), "zzzzz");
      expect(screen.getByText("No matches found")).toBeInTheDocument();
    });
  });

  describe("no search (≤ 5 options)", () => {
    it("does not show search input for ≤ 5 options", async () => {
      const user = userEvent.setup();
      renderDropdown();
      await user.click(screen.getByRole("button"));
      expect(screen.queryByPlaceholderText("Search...")).not.toBeInTheDocument();
    });
  });

  describe("create new", () => {
    it("shows create button when onCreateNew is provided", async () => {
      const user = userEvent.setup();
      renderDropdown({ onCreateNew: vi.fn() });
      await user.click(screen.getByRole("button"));
      expect(screen.getByText("Create new")).toBeInTheDocument();
    });

    it("does not show create button when onCreateNew is not provided", async () => {
      const user = userEvent.setup();
      renderDropdown();
      await user.click(screen.getByRole("button"));
      expect(screen.queryByText("Create new")).not.toBeInTheDocument();
    });

    it("shows input form after clicking create new", async () => {
      const user = userEvent.setup();
      renderDropdown({ onCreateNew: vi.fn() });
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByText("Create new"));
      expect(screen.getByPlaceholderText("Enter name...")).toBeInTheDocument();
    });

    it("calls onCreateNew when confirming creation", async () => {
      const user = userEvent.setup();
      const onCreateNew = vi.fn().mockResolvedValue(undefined);
      renderDropdown({ onCreateNew });
      await user.click(screen.getByRole("button"));
      await user.click(screen.getByText("Create new"));
      const input = screen.getByPlaceholderText("Enter name...");
      await user.type(input, "New Item");
      await user.keyboard("{Enter}");
      expect(onCreateNew).toHaveBeenCalledWith("New Item");
    });
  });

  describe("required", () => {
    it("renders a hidden required input when required", () => {
      renderDropdown({ required: true, value: "" });
      const hiddenInput = document.querySelector('input[required]');
      expect(hiddenInput).toBeInTheDocument();
    });
  });

  describe("empty state", () => {
    it("shows no options message when options array is empty", async () => {
      const user = userEvent.setup();
      renderDropdown({ options: [] });
      await user.click(screen.getByRole("button"));
      expect(screen.getByText("No options available")).toBeInTheDocument();
    });
  });
});
