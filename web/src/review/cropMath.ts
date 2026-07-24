export interface Rect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface Bounds {
  width: number;
  height: number;
}

function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max);
}

export function clipRectToBounds(rect: Rect, bounds: Bounds): Rect {
  const left = clamp(rect.x, 0, bounds.width);
  const top = clamp(rect.y, 0, bounds.height);
  const right = clamp(rect.x + rect.w, 0, bounds.width);
  const bottom = clamp(rect.y + rect.h, 0, bounds.height);

  return {
    x: left,
    y: top,
    w: Math.max(0, right - left),
    h: Math.max(0, bottom - top),
  };
}

export function rectToPercentages(rect: Rect, bounds: Bounds) {
  return {
    left: `${(rect.x / bounds.width) * 100}%`,
    top: `${(rect.y / bounds.height) * 100}%`,
    width: `${(rect.w / bounds.width) * 100}%`,
    height: `${(rect.h / bounds.height) * 100}%`,
  };
}
