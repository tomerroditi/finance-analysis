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
        // generateSW: Workbox builds the SW from JSON config. We previously
        // ran injectManifest with a hand-written src/sw.ts to use a custom
        // fetchDidFail plugin, but that path consistently failed Vercel's
        // build (works locally + GitHub Actions). The network-failure
        // surface is now reproduced client-side via an axios response
        // interceptor in src/services/api.ts, so we don't need the inline
        // plugin and can stay on the simpler, build-portable generateSW
        // strategy.
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
          globPatterns: ["**/*.{js,css,html,svg,png,ico,webmanifest}"],
          maximumFileSizeToCacheInBytes: 10 * 1024 * 1024,
          navigateFallback: "/index.html",
          navigateFallbackDenylist: [/^\/api\//, /^\/docs/, /^\/openapi/],
          cleanupOutdatedCaches: true,
          runtimeCaching: [
            {
              // Cacheable API GETs. Excluded:
              //   /api/scraping/*    real-time scraper state
              //   /api/credentials*  PII (account metadata)
              //   /api/backups       must reflect server truth
              urlPattern: ({ url, request }) =>
                request.method === "GET" &&
                url.pathname.startsWith("/api/") &&
                !url.pathname.startsWith("/api/scraping/") &&
                !url.pathname.startsWith("/api/credentials") &&
                !url.pathname.startsWith("/api/backups"),
              handler: "NetworkFirst",
              options: {
                cacheName: "finance-api-get",
                networkTimeoutSeconds: 4,
                expiration: {
                  maxEntries: 200,
                  maxAgeSeconds: 60 * 60 * 24 * 7,
                },
                cacheableResponse: { statuses: [0, 200] },
              },
            },
          ],
        },
        devOptions: {
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
