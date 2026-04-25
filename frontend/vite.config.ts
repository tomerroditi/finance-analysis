import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Restrict loadEnv to VITE_-prefixed variables so a stray secret in `.env`
  // (DB_PASSWORD, API_KEY, etc.) cannot accidentally be pulled into the
  // client bundle or logged via this config.
  const viteEnv = loadEnv(mode, process.cwd(), "VITE_");
  const port = parseInt(process.env.PORT || "", 10) || 5173;

  return {
    plugins: [
      react(),
      tailwindcss(),
      VitePWA({
        // Use injectManifest so we can hand-write the SW. We need a custom
        // Workbox plugin that broadcasts `API_NETWORK_FAILED` to the page
        // whenever an /api fetch fails (so the user sees a toast even when
        // the SW silently serves stale cache). generateSW serializes the
        // workbox config to JSON and can't carry inline plugin functions.
        strategies: "injectManifest",
        srcDir: "src",
        filename: "sw.ts",
        registerType: "prompt",
        injectRegister: false,
        includeAssets: [
          "favicon.svg",
          "icons/apple-touch-icon.png",
        ],
        manifest: {
          name: "Finance Analysis",
          short_name: "Finance",
          description: "Personal finance tracking and analysis dashboard.",
          theme_color: "#0f172a",
          background_color: "#0f172a",
          display: "standalone",
          orientation: "portrait",
          start_url: "/",
          scope: "/",
          icons: [
            {
              src: "/icons/icon-192.png",
              sizes: "192x192",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/icons/icon-512.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "any",
            },
            {
              src: "/icons/icon-512-maskable.png",
              sizes: "512x512",
              type: "image/png",
              purpose: "maskable",
            },
          ],
        },
        injectManifest: {
          // App shell precaching — JS/CSS/HTML/icons go into the SW cache so
          // first paint works offline and on a flaky connection.
          globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
          // Plotly inflates the main bundle past Workbox's 2 MiB default.
          // Bumped so the entire app shell precaches; revisit once we
          // code-split Plotly off the dashboard route.
          maximumFileSizeToCacheInBytes: 10 * 1024 * 1024,
        },
        devOptions: {
          // The SW is generated only on `vite build`. Keep it disabled in
          // dev to avoid stale cache surprises while iterating.
          enabled: false,
        },
      }),
    ],
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
