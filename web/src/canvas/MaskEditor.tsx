import { useState, type PointerEvent } from "react";
import { Layer, Rect, Stage } from "react-konva";
import { applyPaintAtPoint, countPainted, type MaskGrid } from "./maskModel";

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
  mask: MaskGrid;
  protectedRegions: ProtectedRegion[];
  onChange: (mask: MaskGrid) => void;
  onClear: () => void;
  onUndo?: () => void;
  canUndo?: boolean;
}

function eventToPoint(event: PointerEvent<HTMLDivElement>) {
  const bounds = event.currentTarget.getBoundingClientRect();
  return {
    point: {
      x: event.clientX - bounds.left,
      y: event.clientY - bounds.top,
    },
    surface: {
      width: bounds.width,
      height: bounds.height,
    },
  };
}

export function MaskEditor({
  width,
  height,
  mask,
  protectedRegions,
  onChange,
  onClear,
  onUndo,
  canUndo = false,
}: MaskEditorProps) {
  const [isPainting, setIsPainting] = useState(false);
  const paintedCount = countPainted(mask);

  const paintFromEvent = (event: PointerEvent<HTMLDivElement>) => {
    const { point, surface } = eventToPoint(event);
    onChange(applyPaintAtPoint(mask, point, surface));
  };

  return (
    <section aria-label="mask-editor-panel">
      <div>
        <button type="button" onClick={onClear}>
          Clear mask
        </button>
        <button type="button" onClick={() => onUndo?.()} disabled={!canUndo}>
          Undo mask stroke
        </button>
      </div>
      <p>Painted mask cells: {paintedCount}</p>
      <p>Protected regions: {protectedRegions.length}</p>
      <div style={{ position: "relative", width, height }}>
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
        <div
          aria-label="mask-paint-surface"
          style={{ position: "absolute", inset: 0, cursor: "crosshair" }}
          onPointerDown={(event) => {
            if (event.buttons === 0) {
              return;
            }
            setIsPainting(true);
            paintFromEvent(event);
          }}
          onPointerMove={(event) => {
            if (!isPainting || event.buttons === 0) {
              return;
            }
            paintFromEvent(event);
          }}
          onPointerUp={() => setIsPainting(false)}
          onPointerLeave={() => setIsPainting(false)}
        />
      </div>
    </section>
  );
}
