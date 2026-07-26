import { useEffect, useState } from "react";
import type { JsonObject, Manifest, ReferencePack, Region, SourceSpec, Workflow } from "../api/types";

export interface ManifestControlsProps {
  assets: string[];
  specs: string[];
  providers: string[];
  references: ReferencePack[];
  submitting: boolean;
  onSubmit: (manifest: Manifest) => void;
}

const workflows: Workflow[] = [
  "text_to_portrait",
  "concept_to_portrait",
  "expression_refine",
  "masked_variant",
];

function isWorkflow(value: string): value is Workflow {
  return workflows.some((workflow) => workflow === value);
}

function isJsonScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

const regionKeys = ["x", "y", "w", "h", "label"] as const;

function parseParams(text: string): JsonObject | null {
  try {
    const value: unknown = JSON.parse(text);
    if (
      typeof value !== "object" ||
      value === null ||
      Array.isArray(value) ||
      !Object.values(value).every(isJsonScalar)
    ) {
      return null;
    }
    return Object.fromEntries(Object.entries(value));
  } catch {
    return null;
  }
}

function isRegion(value: unknown): value is Region {
  if (!isRecord(value)) {
    return false;
  }
  const keys = Object.keys(value);
  if (keys.length !== regionKeys.length || !regionKeys.every((key) => keys.includes(key))) {
    return false;
  }
  return (
    typeof value.x === "number" &&
    Number.isInteger(value.x) &&
    value.x >= 0 &&
    typeof value.y === "number" &&
    Number.isInteger(value.y) &&
    value.y >= 0 &&
    typeof value.w === "number" &&
    Number.isInteger(value.w) &&
    value.w > 0 &&
    typeof value.h === "number" &&
    Number.isInteger(value.h) &&
    value.h > 0 &&
    typeof value.label === "string" &&
    value.label.length > 0
  );
}

function parseRegions(text: string): Region[] | null {
  try {
    const value: unknown = JSON.parse(text);
    return Array.isArray(value) && value.every(isRegion) ? value : null;
  } catch {
    return null;
  }
}

function sortedReferences(references: ReferencePack[]): ReferencePack[] {
  return [...references].sort(
    (left, right) => left.id.localeCompare(right.id) || left.revision - right.revision,
  );
}

export function ManifestControls({
  assets,
  specs,
  providers,
  references,
  submitting,
  onSubmit,
}: ManifestControlsProps) {
  const [workflow, setWorkflow] = useState<Workflow>("text_to_portrait");
  const [provider, setProvider] = useState(() => providers[0] ?? "");
  const [referencePack, setReferencePack] = useState("");
  const [referenceRevision, setReferenceRevision] = useState("");
  const [textSource, setTextSource] = useState("");
  const [conceptSource, setConceptSource] = useState("");
  const [approvedPortraitSource, setApprovedPortraitSource] = useState("");
  const [maskPath, setMaskPath] = useState("");
  const [protectedRegions, setProtectedRegions] = useState("[]");
  const [params, setParams] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const referenceOptions = sortedReferences(references);
  const revisions = referenceOptions.filter((reference) => reference.id === referencePack);
  const isRegistryReady =
    assets.includes("portrait") &&
    specs.includes("fe-gba-portrait-standard") &&
    provider.length > 0;

  useEffect(() => {
    if (provider === "" && providers[0]) {
      setProvider(providers[0]);
    }
  }, [provider, providers]);

  const handleSubmit = () => {
    const parsedParams = parseParams(params);
    if (parsedParams === null) {
      setError("Parameters must be a JSON object with string, number, or boolean values.");
      return;
    }
    if (!isRegistryReady) {
      setError("Portrait, the standard target spec, and a provider are required.");
      return;
    }
    const revision = referenceRevision === "" ? null : Number(referenceRevision);
    if (
      (referencePack === "" && revision !== null) ||
      (referencePack !== "" && (!Number.isInteger(revision) || revision === null || revision < 1))
    ) {
      setError("Select a pinned revision for the selected reference pack.");
      return;
    }

    const parsedRegions = parseRegions(protectedRegions);
    if (workflow === "masked_variant" && parsedRegions === null) {
      setError("Protected regions must be a JSON array of valid regions.");
      return;
    }
    if (workflow === "masked_variant" && maskPath.trim() === "") {
      setError("A mask path is required for a masked variant.");
      return;
    }

    const sources: SourceSpec[] = [
      textSource.trim() === "" ? null : { kind: "text", ref: textSource.trim() },
      conceptSource.trim() === "" ? null : { kind: "concept_art", ref: conceptSource.trim() },
      approvedPortraitSource.trim() === ""
        ? null
        : { kind: "approved_portrait", ref: approvedPortraitSource.trim() },
    ].filter((source): source is SourceSpec => source !== null);

    const edit =
      workflow === "masked_variant"
        ? { mask_path: maskPath.trim(), protected_regions: parsedRegions ?? [] }
        : null;
    setError(null);
    onSubmit({
      version: "1.0",
      asset_type: "portrait",
      target_spec: "fe-gba-portrait-standard",
      workflow,
      provider,
      character_ref_pack: referencePack === "" ? null : referencePack,
      character_ref_pack_rev: revision,
      sources,
      edit,
      params: parsedParams,
    });
  };

  return (
    <section aria-label="manifest-controls">
      <h2>Create job</h2>
      <label>
        Workflow
        <select
          value={workflow}
          onChange={(event) => {
            if (isWorkflow(event.target.value)) {
              setWorkflow(event.target.value);
            }
          }}
        >
          {workflows.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Provider
        <select value={provider} onChange={(event) => setProvider(event.target.value)}>
          {providers.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Reference pack
        <select
          value={referencePack}
          onChange={(event) => {
            setReferencePack(event.target.value);
            setReferenceRevision("");
          }}
        >
          <option value="">None</option>
          {Array.from(new Set(referenceOptions.map((reference) => reference.id))).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Reference revision
        <select
          value={referenceRevision}
          disabled={referencePack === ""}
          onChange={(event) => setReferenceRevision(event.target.value)}
        >
          <option value="">Select revision</option>
          {revisions.map((reference) => (
            <option key={reference.revision} value={reference.revision}>
              {reference.revision}
            </option>
          ))}
        </select>
      </label>
      <label>
        Text source
        <input value={textSource} onChange={(event) => setTextSource(event.target.value)} />
      </label>
      <label>
        Concept art source
        <input value={conceptSource} onChange={(event) => setConceptSource(event.target.value)} />
      </label>
      <label>
        Approved portrait source
        <input
          value={approvedPortraitSource}
          onChange={(event) => setApprovedPortraitSource(event.target.value)}
        />
      </label>
      {workflow === "masked_variant" ? (
        <>
          <label>
            Mask path
            <input value={maskPath} onChange={(event) => setMaskPath(event.target.value)} />
          </label>
          <label>
            Protected regions JSON
            <textarea
              value={protectedRegions}
              onChange={(event) => setProtectedRegions(event.target.value)}
            />
          </label>
        </>
      ) : null}
      <label>
        Parameters JSON
        <textarea value={params} onChange={(event) => setParams(event.target.value)} />
      </label>
      {error ? <p role="alert">{error}</p> : null}
      <button type="button" disabled={submitting} onClick={handleSubmit}>
        Create job
      </button>
    </section>
  );
}
