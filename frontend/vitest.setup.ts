import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll, vi } from "vitest";

// Initialize i18n for all tests
import "./src/i18n";
import { server } from "./src/mocks/server";

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

// MSW lifecycle. Tests assume API calls go through the mock server, not the
// network. Unhandled requests log a warning rather than failing the test —
// pages fire many auxiliary calls (analytics, demo-mode toggle, etc.) and
// not every test cares about handling all of them.
beforeAll(() => server.listen({ onUnhandledRequest: "warn" }));
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());
