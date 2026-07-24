import { expect, test } from "vitest";
import { clipRectToBounds, rectToPercentages } from "./cropMath";

test("clips crop rectangles to image bounds", () => {
  expect(clipRectToBounds({ x: -10, y: 20, w: 70, h: 70 }, { width: 100, height: 80 })).toEqual({
    x: 0,
    y: 20,
    w: 60,
    h: 60,
  });
});

test("converts clipped rectangles to percentage styles", () => {
  expect(rectToPercentages({ x: 10, y: 8, w: 40, h: 24 }, { width: 80, height: 48 })).toEqual({
    left: "12.5%",
    top: "16.666666666666664%",
    width: "50%",
    height: "50%",
  });
});
