import { expect, test } from "vitest";
import { applyPaintAtPoint, clearMask, countPainted, emptyMask, paint } from "./maskModel";

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

test("applyPaintAtPoint maps pointer coordinates to immutable cells", () => {
  const mask = applyPaintAtPoint(emptyMask(4, 4), { x: 25, y: 15 }, { width: 40, height: 40 });
  expect(mask[1][2]).toBe(true);
  expect(countPainted(mask)).toBe(1);
});

test("clearMask returns an empty mask with the same size", () => {
  const cleared = clearMask(paint(emptyMask(3, 2), 1, 1));
  expect(cleared).toEqual(emptyMask(3, 2));
});
