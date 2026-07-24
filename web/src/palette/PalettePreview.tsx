import { frameToSvgDataUrl, selectFrame, type IndexedFrame } from "./framePreview";

interface PalettePreviewProps {
  palette: [number, number, number][];
  frames: IndexedFrame[];
  selectedFrameId?: string;
  onSelectFrame?: (frameId: string) => void;
  scale: number;
}

export function PalettePreview({ palette, frames, selectedFrameId, onSelectFrame, scale }: PalettePreviewProps) {
  const selectedFrame = selectFrame(frames, selectedFrameId);

  return (
    <section aria-label="palette-preview">
      <h2>Palette and native-size review</h2>
      {palette.length === 0 ? (
        <p>No palette entries loaded.</p>
      ) : (
        <ul aria-label="palette-entries" style={{ display: "flex", gap: 8, padding: 0 }}>
          {palette.map(([r, g, b], index) => (
            <li key={`${r}-${g}-${b}-${index}`} style={{ listStyle: "none" }}>
              <span
                aria-label={`palette-entry-${index}`}
                style={{
                  display: "inline-block",
                  width: 18,
                  height: 18,
                  border: "1px solid currentColor",
                  backgroundColor: `rgb(${r}, ${g}, ${b})`,
                }}
              />
            </li>
          ))}
        </ul>
      )}
      {frames.length === 0 ? (
        <p>No eye or mouth frames available.</p>
      ) : (
        <fieldset>
          <legend>Eye and mouth frames</legend>
          {frames.map((frame) => (
            <label key={frame.id}>
              <input
                type="radio"
                name="frame-preview"
                checked={selectedFrame?.id === frame.id}
                onChange={() => onSelectFrame?.(frame.id)}
              />
              {frame.label}
            </label>
          ))}
        </fieldset>
      )}
      {selectedFrame ? (
        <>
          <img

            alt={`${selectedFrame.label} preview`}
            src={frameToSvgDataUrl(selectedFrame, palette)}
            width={selectedFrame.width * scale}
            height={selectedFrame.height * scale}
            style={{ imageRendering: "pixelated" }}
          />
          <p>
            Native size {selectedFrame.width}×{selectedFrame.height} at scale {scale}×
          </p>
        </>
      ) : null}
    </section>
  );
}
