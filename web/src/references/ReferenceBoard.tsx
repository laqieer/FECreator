interface ReferenceBoardProps {
  swatches: string[];
  manifestText: string;
  onManifestChange: (value: string) => void;
}

export function ReferenceBoard({ swatches, manifestText, onManifestChange }: ReferenceBoardProps) {
  return (
    <section aria-label="reference-board">
      <h2>Reference board</h2>
      {swatches.length === 0 ? (
        <p>No reference swatches loaded.</p>
      ) : (
        <ul aria-label="reference-colors">
          {swatches.map((hex, index) => (
            <li key={`${hex}-${index}`}>
              <span
                aria-label={`swatch ${hex}`}
                title={hex}
                style={{
                  display: "inline-block",
                  width: 20,
                  height: 20,
                  border: "1px solid currentColor",
                  backgroundColor: hex,
                  verticalAlign: "middle",
                  marginRight: 8,
                }}
              />
              <span>{hex}</span>
            </li>
          ))}
        </ul>
      )}
      <label>
        Manifest JSON
        <textarea
          rows={12}
          value={manifestText}
          onChange={(event) => onManifestChange(event.target.value)}
        />
      </label>
    </section>
  );
}
