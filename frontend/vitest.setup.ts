import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// Initialize i18n for all tests
import "./src/i18n";

// Mock react-plotly.js globally — Plotly requires browser canvas APIs not available in happy-dom
vi.mock("react-plotly.js", () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    const testId =
      typeof props["data-testid"] === "string"
        ? props["data-testid"]
        : "plotly-chart";
    return `<div data-testid="${testId}" />`;
  },
}));

// Mock window.ResizeObserver for components that use it
if (typeof globalThis.ResizeObserver === "undefined") {
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

afterEach(() => {
  cleanup();
});
