import { expect, test } from "vitest";
import { buildFrameSvgMarkup, type IndexedFrame } from "./framePreview";

const frame: IndexedFrame = {
  id: "eyes-open",
  label: "Eyes open",
  kind: "eyes",
  width: 2,
  height: 2,
  pixels: [
    [0, 1],
    [1, 0],
  ],
};

test("buildFrameSvgMarkup paints indexed pixels with palette colors", () => {
  const svg = buildFrameSvgMarkup(frame, [
    [0, 0, 0],
    [255, 0, 0],
  ]);

  expect(svg).toContain('viewBox="0 0 2 2"');
  expect(svg).toContain('fill="rgb(255,0,0)"');
});
