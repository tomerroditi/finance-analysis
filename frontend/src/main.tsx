import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "./i18n";
import "./index.css";
import App from "./App.tsx";

// Pages are lazy chunks. A client still running the previous build asks for
// chunk hashes a redeploy has removed; reload once to pick up the new index.
window.addEventListener("vite:preloadError", (event) => {
  const key = "fad_chunk_reload";
  if (sessionStorage.getItem(key)) return;
  event.preventDefault();
  sessionStorage.setItem(key, "1");
  window.location.reload();
});
window.addEventListener("load", () =>
  sessionStorage.removeItem("fad_chunk_reload"),
);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
