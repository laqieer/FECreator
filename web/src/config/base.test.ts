import { expect, test } from "vitest";
import { resolveBase } from "./base";

test("demo mode resolves the project pages base path", () => {
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "demo" })).toBe("/FECreator/");
});

test("missing mode resolves the root base path", () => {
  expect(resolveBase({})).toBe("/");
});

test("any non-demo value fails closed to the root base path", () => {
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "local" })).toBe("/");
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "DEMO" })).toBe("/");
  expect(resolveBase({ VITE_FE_CREATOR_MODE: "" })).toBe("/");
});