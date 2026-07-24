import { expect, test } from "vitest";
import { countPainted, emptyMask, paint } from "./maskModel";

test("empty mask has no painted cells", () => {
  expect(countPainted(emptyMask(4, 3))).toBe(0);
});

test("paint marks a cell once", () => {
  let mask = emptyMask(4, 4);
  mask = paint(mask, 1, 2);
  mask = paint(mask, 1, 2);
  expect(countPainted(mask)).toBe(1);
});

test("paint ignores coordinates outside the mask", () => {
  const mask = paint(emptyMask(2, 2), 7, 7);
  expect(countPainted(mask)).toBe(0);
});
