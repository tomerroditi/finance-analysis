import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { SpeedInsights } from "@vercel/speed-insights/react";
import { Analytics } from "@vercel/analytics/react";
import "./i18n";
import "./index.css";
import App from "./App.tsx";

// Polyfill for Plotly
if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).global = window;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
    <SpeedInsights />
    <Analytics />
  </StrictMode>,
);
