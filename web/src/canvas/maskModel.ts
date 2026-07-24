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

export function countPainted(mask: MaskGrid): number {
  return mask.reduce((total, row) => total + row.filter(Boolean).length, 0);
}
