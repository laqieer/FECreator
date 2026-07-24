export type MaskGrid = boolean[][];

export function emptyMask(width: number, height: number): MaskGrid {
  return Array.from({ length: height }, () => Array.from({ length: width }, () => false));
}

export function paint(mask: MaskGrid, x: number, y: number): MaskGrid {
  const next = mask.map((row) => [...row]);
  if (y < 0 || y >= next.length || x < 0 || next.length === 0 || x >= next[0].length) {
    return next;
  }

  next[y][x] = true;
  return next;
}

export function clearMask(mask: MaskGrid): MaskGrid {
  return emptyMask(mask[0]?.length ?? 0, mask.length);
}

export function applyPaintAtPoint(
  mask: MaskGrid,
  point: { x: number; y: number },
  surface: { width: number; height: number },
): MaskGrid {
  if (mask.length === 0 || mask[0]?.length === 0 || surface.width <= 0 || surface.height <= 0) {
    return mask.map((row) => [...row]);
  }

  const width = mask[0].length;
  const height = mask.length;
  const x = Math.min(width - 1, Math.max(0, Math.floor((point.x / surface.width) * width)));
  const y = Math.min(height - 1, Math.max(0, Math.floor((point.y / surface.height) * height)));
  return paint(mask, x, y);
}

export function countPainted(mask: MaskGrid): number {
  return mask.reduce((total, row) => total + row.filter(Boolean).length, 0);
}
