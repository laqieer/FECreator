import { useMemo } from "react";
import { Layer, Rect, Stage } from "react-konva";
import { countPainted, emptyMask } from "./maskModel";

interface ProtectedRegion {
  x: number;
  y: number;
  w: number;
  h: number;
  label: string;
}

interface MaskEditorProps {
  width: number;
  height: number;
  protectedRegions: ProtectedRegion[];
}

export function MaskEditor({ width, height, protectedRegions }: MaskEditorProps) {
  const paintedCount = useMemo(() => countPainted(emptyMask(width, height)), [height, width]);

  return (
    <section aria-label="mask-editor-panel">
      <p>Painted mask cells: {paintedCount}</p>
      <p>Protected regions: {protectedRegions.length}</p>
      <Stage width={width} height={height}>
        <Layer>
          {protectedRegions.map((region) => (
            <Rect
              key={region.label}
              name={region.label}
              x={region.x}
              y={region.y}
              width={region.w}
              height={region.h}
              stroke="#2f6fed"
            />
          ))}
        </Layer>
      </Stage>
    </section>
  );
}
