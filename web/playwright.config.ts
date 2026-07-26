import { defineConfig, devices } from "@playwright/test";
import {
  demoBaseUrl,
  demoBasePath,
  demoPort,
  localBaseUrl,
  repoRoot,
  serveCommand,
  serveEnv,
  webRoot,
} from "./e2e/env";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: process.env.CI ? [["github"], ["list"]] : [["list"]],
  globalSetup: "./e2e/globalSetup.ts",
  globalTeardown: "./e2e/globalTeardown.ts",
  expect: { timeout: 15_000 },
  timeout: 120_000,
  use: {
    ...devices["Desktop Chrome"],
    trace: "retain-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "local",
      testMatch: /workbench\.local\.spec\.ts/,
      use: { baseURL: localBaseUrl },
    },
    {
      name: "demo",
      testMatch: /workbench\.demo\.spec\.ts/,
      use: { baseURL: `${demoBaseUrl}${demoBasePath}` },
    },
  ],
  webServer: [
    {
      // The packaged local app: FastAPI serves both /api and the built assets.
      command: serveCommand,
      cwd: repoRoot,
      env: serveEnv,
      url: `${localBaseUrl}/api/specs`,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
    {
      // The static demo build, served from its own out directory so it never
      // overwrites the local build in src/fecreator/_web.
      command: `npm run preview:demo -- --port ${demoPort}`,
      cwd: webRoot,
      url: `${demoBaseUrl}${demoBasePath}`,
      reuseExistingServer: false,
      stdout: "pipe",
      stderr: "pipe",
      timeout: 120_000,
    },
  ],
});
