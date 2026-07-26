import { useMemo, useState } from "react";
import type { ReferencePack } from "../api/types";

export interface ReferenceSelection {
  id: string;
  revision: number;
}

interface ReferenceBoardProps {
  swatches?: string[];
  references?: ReferencePack[];
  selectedReference?: ReferenceSelection | null;
  onSelectReference?: (selection: ReferenceSelection | null) => void;
  manifestText: string;
  onManifestChange: (value: string) => void;
}

export function ReferenceBoard({
  swatches = [],
  references = [],
  selectedReference,
  onSelectReference,
  manifestText,
  onManifestChange,
}: ReferenceBoardProps) {
  const [localSelection, setLocalSelection] = useState<ReferenceSelection | null>(null);
  const selection = selectedReference === undefined ? localSelection : selectedReference;
  const selectedPack = useMemo(
    () =>
      references.find(
        (reference) =>
          reference.id === selection?.id && reference.revision === selection.revision,
      ) ?? null,
    [references, selection],
  );
  const currentSwatches = selectedPack?.swatches ?? swatches;
  const referenceIds = [...new Set(references.map((reference) => reference.id))];
  const revisions = references.filter((reference) => reference.id === selection?.id);

  const select = (next: ReferenceSelection | null) => {
    setLocalSelection(next);
    onSelectReference?.(next);
  };

  return (
    <section aria-label="reference-board">
      <h2>Reference board</h2>
      {references.length > 0 ? (
        <div>
          <label>
            Reference pack
            <select
              value={selection?.id ?? ""}
              onChange={(event) => {
                if (event.target.value === "") {
                  select(null);
                  return;
                }
                const firstRevision = references.find((reference) => reference.id === event.target.value);
                if (firstRevision) {
                  select({ id: firstRevision.id, revision: firstRevision.revision });
                }
              }}
            >
              <option value="">Select reference</option>
              {referenceIds.map((id) => (
                <option key={id} value={id}>
                  {id}
                </option>
              ))}
            </select>
          </label>
          <label>
            Reference revision
            <select
              value={selection?.revision ?? ""}
              onChange={(event) => {
                const revision = Number(event.target.value);
                if (Number.isInteger(revision) && selection) {
                  select({ id: selection.id, revision });
                }
              }}
            >
              {revisions.map((reference) => (
                <option key={reference.revision} value={reference.revision}>
                  {reference.revision}
                </option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
      {currentSwatches.length === 0 ? (
        <p>No reference swatches loaded.</p>
      ) : (
        <ul aria-label="reference-colors">
          {currentSwatches.map((hex, index) => (
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
