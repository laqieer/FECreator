import { frameToSvgDataUrl, selectFrame, type IndexedFrame } from "./framePreview";

const expressionCells = [
  { id: "half_closed_eyes", label: "Half-closed eyes", x: 96, y: 48, w: 32, h: 16 },
  { id: "closed_eyes", label: "Closed eyes", x: 96, y: 64, w: 32, h: 16 },
  { id: "mouth1", label: "Mouth 1", x: 0, y: 80, w: 32, h: 16 },
  { id: "mouth2", label: "Mouth 2", x: 32, y: 80, w: 32, h: 16 },
  { id: "mouth3", label: "Mouth 3", x: 64, y: 80, w: 32, h: 16 },
  { id: "mouth4_status", label: "Mouth 4 status", x: 96, y: 80, w: 32, h: 16 },
  { id: "mouth5", label: "Mouth 5", x: 0, y: 96, w: 32, h: 16 },
  { id: "mouth6", label: "Mouth 6", x: 32, y: 96, w: 32, h: 16 },
  { id: "mouth7", label: "Mouth 7", x: 64, y: 96, w: 32, h: 16 },
] as const;

interface PalettePreviewProps {
  palette?: [number, number, number][];
  frames?: IndexedFrame[];
  artifacts?: Array<{ role: string; path: string; url: string }>;
  selectedFrameId?: string;
  onSelectFrame?: (frameId: string) => void;
  scale?: number;
}

export function PalettePreview({
  palette = [],
  frames = [],
  artifacts = [],
  selectedFrameId,
  onSelectFrame,
  scale = 1,
}: PalettePreviewProps) {
  const selectedFrame = selectFrame(frames, selectedFrameId);
  const portrait =
    artifacts.find((artifact) => artifact.role === "sheet") ??
    artifacts.find((artifact) => artifact.role === "portrait") ??
    artifacts[0];
  const expressionArtifacts = artifacts.filter((artifact) =>
    /eye|mouth|expression/.test(artifact.role),
  );

  return (
    <section aria-label="palette-preview">
      <h2>Palette and native-size review</h2>
      {portrait ? (
        <>
          <figure>
            <div style={{ position: "relative", width: 128, height: 112 }}>
              <img
                alt="Candidate native-size preview"
                src={portrait.url}
                width={128}
                height={112}
                style={{ imageRendering: "pixelated" }}
              />
              <div
                aria-label="target-spec-overlay"
                style={{
                  position: "absolute",
                  inset: 0,
                  border: "2px solid #2f6fed",
                  pointerEvents: "none",
                }}
              />
            </div>
            <figcaption>Native target size 128×112</figcaption>
          </figure>
          <section aria-label="candidate-expression-cells">
            <h3>Candidate expression cells</h3>
            <ul>
              {expressionCells.map((cell) => (
                <li key={cell.id}>
                  <div
                    aria-label={`${cell.id} expression cell`}
                    style={{ width: cell.w, height: cell.h, overflow: "hidden", position: "relative" }}
                  >
                    <img
                      alt=""
                      aria-hidden="true"
                      src={portrait.url}
                      width={128}
                      height={112}
                      style={{
                        imageRendering: "pixelated",
                        left: -cell.x,
                        position: "absolute",
                        top: -cell.y,
                      }}
                    />
                  </div>
                  <span>{cell.label}</span>
                </li>
              ))}
            </ul>
          </section>
        </>
      ) : null}
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
      {expressionArtifacts.length > 0 ? (
        <section aria-label="candidate-expression-artifacts">
          <h3>Candidate expression artifacts</h3>
          <ul>
            {expressionArtifacts.map((artifact) => (
              <li key={artifact.path}>
                <img alt={`${artifact.role} ${artifact.path}`} src={artifact.url} />
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </section>
  );
}
