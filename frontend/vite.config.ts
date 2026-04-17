import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Restrict loadEnv to VITE_-prefixed variables so a stray secret in `.env`
  // (DB_PASSWORD, API_KEY, etc.) cannot accidentally be pulled into the
  // client bundle or logged via this config.
  const viteEnv = loadEnv(mode, process.cwd(), "VITE_");
  const port = parseInt(process.env.PORT || "", 10) || 5173;

  return {
    plugins: [react(), tailwindcss()],
    server: {
      port,
      proxy: {
        "/api": {
          target: viteEnv.VITE_BACKEND_URL || "http://127.0.0.1:8000",
          changeOrigin: true,
        },
      },
    },
  };
});
