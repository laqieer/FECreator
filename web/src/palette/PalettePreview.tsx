interface PalettePreviewProps {
  palette: [number, number, number][];
  scale: number;
}

const nativeWidth = 128;
const nativeHeight = 112;

export function PalettePreview({ palette, scale }: PalettePreviewProps) {
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
      <div
        aria-label="native-size-preview"
        style={{
          width: nativeWidth * scale,
          height: nativeHeight * scale,
          border: "1px solid currentColor",
          backgroundImage: "linear-gradient(45deg, #ddd 25%, transparent 25%, transparent 75%, #ddd 75%), linear-gradient(45deg, #ddd 25%, transparent 25%, transparent 75%, #ddd 75%)",
          backgroundPosition: "0 0, 8px 8px",
          backgroundSize: "16px 16px",
          imageRendering: "pixelated",
        }}
      />
      <p>Native size 128×112 at scale {scale}×</p>
      <h3>Eye and mouth review</h3>
      <ul>
        <li>Eyes aligned with the portrait mask window.</li>
        <li>Mouth centered for talk animation slices.</li>
      </ul>
    </section>
  );
}
