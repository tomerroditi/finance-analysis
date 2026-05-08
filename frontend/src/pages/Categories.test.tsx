import { describe, it, expect } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { Categories } from "./Categories";

describe("Categories", () => {
  describe("rendering", () => {
    it("renders the page heading", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        // Title renders as "Categories" (translated) or "categories.title" (key fallback)
        const h1 = document.querySelector("h1");
        expect(h1).toBeInTheDocument();
      });
    });
  });

  describe("category list", () => {
    it("displays categories from the API", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByText("Food")).toBeInTheDocument();
        expect(screen.getByText("Transport")).toBeInTheDocument();
      });
    });

    it("displays tags within categories after expanding", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByText("Food")).toBeInTheDocument();
      });
      // The h3 stopsPropagation to handle inline rename, so click the outer
      // header row (identified by data-testid) to expand the accordion.
      fireEvent.click(screen.getByTestId("category-header-Food"));
      await waitFor(() => {
        expect(screen.getByText("Groceries")).toBeInTheDocument();
        expect(screen.getByText("Restaurants")).toBeInTheDocument();
      });
    });

    it("displays protected categories", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByText("Salary")).toBeInTheDocument();
        expect(screen.getByText("Investments")).toBeInTheDocument();
      });
    });
  });
});
