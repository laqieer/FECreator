import { expect, test } from "vitest";

import { App } from "../main";

test("App is defined", () => {
  expect(typeof App).toBe("function");
});
