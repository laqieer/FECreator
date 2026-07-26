import { useEffect, useState, type KeyboardEvent, type PointerEvent } from "react";
import { Layer, Rect, Stage } from "react-konva";
import type { EditSpec, Region } from "../api/types";
import { applyPaintAtPoint, countPainted, paint, type MaskGrid } from "./maskModel";

export type MaskDraft = EditSpec;

interface MaskEditorProps {
  width: number;
  height: number;
  mask: MaskGrid;
  maskPath?: string;
  protectedRegions: Region[];
  onChange: (mask: MaskGrid) => void;
  onDraftChange?: (draft: MaskDraft) => void;
  onProtectedRegionsChange?: (regions: Region[]) => void;
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
  maskPath,
  protectedRegions,
  onChange,
  onDraftChange,
  onProtectedRegionsChange,
  onClear,
  onUndo,
  canUndo = false,
}: MaskEditorProps) {
  const [isPainting, setIsPainting] = useState(false);
  const [cursor, setCursor] = useState({ x: 0, y: 0 });
  const [localMaskPath, setLocalMaskPath] = useState(maskPath ?? "masks/draft.png");
  const [newRegion, setNewRegion] = useState({ x: "", y: "", w: "", h: "", label: "" });
  const [regionError, setRegionError] = useState<string | null>(null);
  const paintedCount = countPainted(mask);
  const draftMaskPath = maskPath ?? localMaskPath;

  useEffect(() => {
    if (maskPath !== undefined) {
      setLocalMaskPath(maskPath);
    }
  }, [maskPath]);

  const emitDraft = (regions = protectedRegions, nextMaskPath = draftMaskPath) => {
    onDraftChange?.({ mask_path: nextMaskPath, protected_regions: regions });
  };

  const paintFromEvent = (event: PointerEvent<HTMLDivElement>) => {
    const { point, surface } = eventToPoint(event);
    onChange(applyPaintAtPoint(mask, point, surface));
    emitDraft();
  };

  const paintAtCursor = () => {
    onChange(paint(mask, cursor.x, cursor.y));
    emitDraft();
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      setCursor((current) => ({ ...current, x: Math.min(width - 1, current.x + 1) }));
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      setCursor((current) => ({ ...current, x: Math.max(0, current.x - 1) }));
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor((current) => ({ ...current, y: Math.min(height - 1, current.y + 1) }));
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor((current) => ({ ...current, y: Math.max(0, current.y - 1) }));
    } else if (event.key === " " || event.key === "Space" || event.key === "Enter") {
      event.preventDefault();
      paintAtCursor();
    }
  };

  const addProtectedRegion = () => {
    if (
      newRegion.x.trim() === "" ||
      newRegion.y.trim() === "" ||
      newRegion.w.trim() === "" ||
      newRegion.h.trim() === ""
    ) {
      setRegionError("Enter a label and non-negative integer region bounds.");
      return;
    }
    const region: Region = {
      x: Number(newRegion.x),
      y: Number(newRegion.y),
      w: Number(newRegion.w),
      h: Number(newRegion.h),
      label: newRegion.label.trim(),
    };
    if (
      !Number.isInteger(region.x) ||
      !Number.isInteger(region.y) ||
      !Number.isInteger(region.w) ||
      !Number.isInteger(region.h) ||
      region.x < 0 ||
      region.y < 0 ||
      region.w <= 0 ||
      region.h <= 0 ||
      region.label === ""
    ) {
      setRegionError("Enter a label and non-negative integer region bounds.");
      return;
    }
    const next = [...protectedRegions, region];
    onProtectedRegionsChange?.(next);
    emitDraft(next);
    setNewRegion({ x: "", y: "", w: "", h: "", label: "" });
    setRegionError(null);
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
      <label>
        Mask path
        <input
          value={draftMaskPath}
          onChange={(event) => {
            setLocalMaskPath(event.target.value);
            onDraftChange?.({ mask_path: event.target.value, protected_regions: protectedRegions });
          }}
        />
      </label>
      <fieldset>
        <legend>Add protected region</legend>
        {(["x", "y", "w", "h", "label"] as const).map((key) => (
          <label key={key}>
            {key}
            <input
              value={newRegion[key]}
              onChange={(event) => setNewRegion((current) => ({ ...current, [key]: event.target.value }))}
            />
          </label>
        ))}
        <button type="button" onClick={addProtectedRegion}>
          Add protected region
        </button>
      </fieldset>
      {regionError ? <p role="alert">{regionError}</p> : null}
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
          aria-describedby="mask-keyboard-help"
          aria-roledescription="mask paint surface"
          role="application"
          tabIndex={0}
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
          onKeyDown={handleKeyDown}
        />
      </div>
      <p id="mask-keyboard-help">
        Use arrow keys to move the mask cursor and Space or Enter to paint a cell.
      </p>
    </section>
  );
}
