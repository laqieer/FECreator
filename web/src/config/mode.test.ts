import { afterEach, expect, test, vi } from "vitest";
import { appMode, isDemo } from "./mode";

afterEach(() => {
  vi.unstubAllEnvs();
});

test("the demo environment variable selects demo mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "demo");
  expect(appMode()).toBe("demo");
  expect(isDemo()).toBe(true);
});

test("an empty environment variable fails closed to local mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "");
  expect(appMode()).toBe("local");
  expect(isDemo()).toBe(false);
});

test("an unrecognized value fails closed to local mode", () => {
  vi.stubEnv("VITE_FE_CREATOR_MODE", "production");
  expect(appMode()).toBe("local");
});