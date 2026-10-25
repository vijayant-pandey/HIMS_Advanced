/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig, loadEnv } from "vite";

// The dev server proxies the API so the session and CSRF cookies stay same-origin,
// matching the CloudFront/ALB topology used in managed environments (spec 17, 30.2).
// `npm run dev` serves the default local hospital; `npm run dev:us` serves the US deployment
// (settings in .env.us).
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ".", "VITE_");
  return {
    plugins: [react()],
    server: {
      port: Number(env.VITE_DEV_PORT ?? 5173),
      strictPort: true,
      proxy: {
        "/api": { target: env.VITE_API_TARGET ?? "http://localhost:8000", changeOrigin: false },
      },
    },
    build: {
      sourcemap: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
      setupFiles: ["./src/test/setup.ts"],
    },
  };
});
