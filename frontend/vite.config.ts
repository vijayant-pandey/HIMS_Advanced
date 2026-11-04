import react from "@vitejs/plugin-react";
import { readFileSync } from "node:fs";
import { defineConfig, loadEnv } from "vite";
import { configDefaults } from "vitest/config";

// The dev server proxies the API so the session and CSRF cookies stay same-origin,
// matching the CloudFront/ALB topology used in managed environments (spec 17, 30.2).
// `npm run dev` serves the default local hospital; `npm run dev:us` serves the US deployment
// (settings in .env.us).
// Browser protection headers (HIMS-SEC-012). `vite preview` serves the production build with the
// exact headers hosting must send. The dev server needs inline start-up code and its live-reload
// connection, so it allows those and does not send reports.
const productionHeaders: Record<string, string> = JSON.parse(
  readFileSync(new URL("./security-headers.json", import.meta.url), "utf8"),
);
const devHeaders: Record<string, string> = {
  ...productionHeaders,
  "Content-Security-Policy": productionHeaders["Content-Security-Policy"]!
    .replace("script-src 'self'", "script-src 'self' 'unsafe-inline'")
    .replace("connect-src 'self'", "connect-src 'self' ws: wss:")
    .replace(/; report-uri [^;]+/, ""),
};
// HTTPS-only rule: browsers ignore it over plain http, and local work never uses https.
delete devHeaders["Strict-Transport-Security"];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_PORT ?? 5173),
      strictPort: true,
      headers: devHeaders,
      proxy: {
        "/api": { target: env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false },
      },
    },
    preview: {
      headers: productionHeaders,
    },
    build: {
      sourcemap: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
      // Browser tests (e2e/) run with Playwright, not Vitest (HIMS-QA-001).
      exclude: [...configDefaults.exclude, "e2e/**"],
    },
  };
});
