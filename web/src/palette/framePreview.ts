export interface IndexedFrame {
  id: string;
  label: string;
  kind: "eyes" | "mouth";
  width: number;
  height: number;
  pixels: number[][];
}

export function buildFrameSvgMarkup(frame: IndexedFrame, palette: [number, number, number][]) {
  const rects = frame.pixels.flatMap((row, y) =>
    row.map((paletteIndex, x) => {
      const [r, g, b] = palette[paletteIndex] ?? [255, 0, 255];
      return `<rect x="${x}" y="${y}" width="1" height="1" fill="rgb(${r},${g},${b})" />`;
    }),
  );

  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${frame.width} ${frame.height}" shape-rendering="crispEdges">${rects.join("")}</svg>`;
}

export function frameToSvgDataUrl(frame: IndexedFrame, palette: [number, number, number][]) {
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(buildFrameSvgMarkup(frame, palette))}`;
}

export function selectFrame(frames: IndexedFrame[], selectedFrameId?: string) {
  if (frames.length === 0) {
    return null;
  }

  return frames.find((frame) => frame.id === selectedFrameId) ?? frames[0];
}
