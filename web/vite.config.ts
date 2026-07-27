import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { resolveBase } from "./src/config/base";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd());
  return {
    base: resolveBase(env),
    plugins: [react()],
    build: {
      outDir: "../src/fecreator/_web",
      emptyOutDir: true,
    },
    test: {
      environment: "jsdom",
      globals: true,
      include: ["src/**/*.{test,spec}.{ts,tsx}", "e2e/**/*.test.ts"],
    },
  };
});
