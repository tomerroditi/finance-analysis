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
        workbox: {
          // App shell precaching — JS/CSS/HTML/icons go into the SW cache so
          // first paint works offline and on a flaky connection.
          globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
          // Plotly inflates the main bundle past Workbox's 2 MiB default.
          // Bumped so the entire app shell precaches; revisit once we
          // code-split Plotly off the dashboard route.
          maximumFileSizeToCacheInBytes: 10 * 1024 * 1024,
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/openapi/],
          cleanupOutdatedCaches: true,
          // API GETs that are safe to read while offline. Mutations and the
          // scraping status endpoint are intentionally not cached: see
          // `runtimeCaching` exclusions below.
          runtimeCaching: [
            {
              urlPattern: ({ url, request }) =>
                request.method === "GET" &&
                url.pathname.startsWith("/api/") &&
                !url.pathname.startsWith("/api/scraping/status") &&
                !url.pathname.startsWith("/api/scraping/start") &&
                !url.pathname.startsWith("/api/backups"),
              handler: "NetworkFirst",
              options: {
                cacheName: "finance-api-get",
                networkTimeoutSeconds: 4,
                expiration: {
                  maxEntries: 200,
                  maxAgeSeconds: 60 * 60 * 24 * 7, // 7 days
                },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
          ],
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
