import { describe, it, expect } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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
      const user = userEvent.setup();
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByText("Food")).toBeInTheDocument();
      });
      // Categories collapse their tags by default; tap the row to reveal them.
      await user.click(screen.getByText("Food"));
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
