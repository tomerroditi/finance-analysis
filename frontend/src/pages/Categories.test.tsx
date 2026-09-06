import { describe, it, expect } from "vitest";
import { screen, waitFor, fireEvent } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../mocks/server";
import { renderWithProviders } from "../test-utils";
import { Categories } from "./Categories";

describe("Categories", () => {
  describe("rendering", () => {
    it("renders the new-category action", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(
          screen.getByRole("button", { name: /categories\.newCategory|new category/i }),
        ).toBeInTheDocument();
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

  describe("unused categories", () => {
    it("does not render the section when every category is in use", async () => {
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      });
      expect(
        screen.queryByTestId("unused-categories-toggle"),
      ).not.toBeInTheDocument();
    });

    it("moves unused categories out of the main grid and into the section", async () => {
      server.use(
        http.get("/api/tagging/categories/usage", () =>
          HttpResponse.json({
            Food: { last_used: "2026-08-01", unused: false },
            Transport: { last_used: "2025-01-05", unused: true },
          }),
        ),
      );
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
      });
      expect(screen.getByTestId("category-card-Food")).toBeInTheDocument();
      expect(screen.queryByTestId("category-card-Transport")).not.toBeInTheDocument();

      fireEvent.click(screen.getByTestId("unused-categories-toggle"));
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Transport")).toBeInTheDocument();
      });
    });

    it("auto-expands the section when a search matches an unused category", async () => {
      server.use(
        http.get("/api/tagging/categories/usage", () =>
          HttpResponse.json({
            Food: { last_used: "2026-08-01", unused: false },
            Transport: { last_used: "2025-01-05", unused: true },
          }),
        ),
      );
      renderWithProviders(<Categories />);
      await waitFor(() => {
        expect(screen.getByTestId("unused-categories-toggle")).toBeInTheDocument();
      });
      expect(screen.queryByTestId("category-card-Transport")).not.toBeInTheDocument();

      fireEvent.change(
        screen.getByPlaceholderText(/searchPlaceholder|search categories/i),
        { target: { value: "Transport" } },
      );
      await waitFor(() => {
        expect(screen.getByTestId("category-card-Transport")).toBeInTheDocument();
      });
    });
  });
});
