import { describe, it, expect } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "../test-utils";
import { Categories } from "./Categories";

describe("Categories", () => {
  describe("rendering", () => {
    it("renders the page heading", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        const h1 = document.querySelector("h1");
        expect(h1).toBeInTheDocument();
      });
    });
  });

  describe("category grid", () => {
    it("displays category cards from the API", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
        expect(screen.getByTestId("category-card-Transport")).toBeInTheDocument();
      });
    });

    it("displays tags inside the detail panel when a card is clicked", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId("category-card-Food"));
      await waitFor(() => {
        expect(screen.getByText("Groceries")).toBeInTheDocument();
        expect(screen.getByText("Restaurants")).toBeInTheDocument();
      });
    });

    it("closes the detail panel when backdrop is clicked", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      });
      fireEvent.click(screen.getByTestId("category-card-Food"));
      await waitFor(() => {
        expect(screen.getByTestId("category-panel")).toBeInTheDocument();
      });
      const panel = screen.getByTestId("category-panel");
      const backdrop = panel.parentElement!;
      fireEvent.click(backdrop);
      await waitFor(() => {
        expect(screen.queryByTestId("category-panel")).not.toBeInTheDocument();
      });
    });

    it("displays protected categories as cards", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Salary")).toBeInTheDocument();
        expect(screen.getByTestId("category-card-Investments")).toBeInTheDocument();
      });
    });
  });
});
