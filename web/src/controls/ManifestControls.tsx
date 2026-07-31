import { useEffect, useState } from "react";
import type {
  AssetMetadata,
  AssetType,
  JsonObject,
  Manifest,
  ReferencePack,
  Region,
  SourceSpec,
  Workflow,
} from "../api/types";
import { portableStorageIdError } from "../validation/storageId";

export interface ManifestControlsProps {
  assets: string[];
  specs: string[];
  providers: string[];
  references: ReferencePack[];
  selectedReference?: { id: string; revision: number } | null;
  onSelectedReferenceChange?: (selection: { id: string; revision: number } | null) => void;
  submitting: boolean;
  onSubmit: (manifest: Manifest) => void;
}

interface AssetControlConfig {
  targetSpec: Manifest["target_spec"];
  workflows: readonly Workflow[];
  approvedSourceKind: SourceSpec["kind"];
  approvedSourceLabel: string;
}

const assetConfigs = {
  portrait: {
    targetSpec: "fe-gba-portrait-standard",
    workflows: [
      "text_to_portrait",
      "concept_to_portrait",
      "expression_refine",
      "masked_variant",
    ],
    approvedSourceKind: "approved_portrait",
    approvedSourceLabel: "Approved portrait source",
  },
  dialogue_background: {
    targetSpec: "fe8-dialogue-background-source-240x160",
    workflows: [
      "text_to_dialogue_background",
      "concept_to_dialogue_background",
      "masked_variant",
    ],
    approvedSourceKind: "approved_dialogue_background",
    approvedSourceLabel: "Approved dialogue background source",
  },
} satisfies Record<AssetType, AssetControlConfig>;

const approvedBaseWorkflows: readonly Workflow[] = ["expression_refine", "masked_variant"];

function isAssetType(value: string): value is AssetType {
  return value === "portrait" || value === "dialogue_background";
}

function isWorkflow(value: string, assetType: AssetType): value is Workflow {
  return assetConfigs[assetType].workflows.some((workflow) => workflow === value);
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
  selectedReference,
  onSelectedReferenceChange,
  submitting,
  onSubmit,
}: ManifestControlsProps) {
  const [assetType, setAssetType] = useState<AssetType>(
    () => assets.find(isAssetType) ?? "portrait",
  );
  const [workflow, setWorkflow] = useState<Workflow>(
    () => assetConfigs[assets.find(isAssetType) ?? "portrait"].workflows[0],
  );
  const [provider, setProvider] = useState(() => providers[0] ?? "");
  const [referencePack, setReferencePack] = useState("");
  const [referenceRevision, setReferenceRevision] = useState("");
  const [textSource, setTextSource] = useState("");
  const [conceptSource, setConceptSource] = useState("");
  const [approvedAssetSource, setApprovedAssetSource] = useState("");
  const [parentAssetId, setParentAssetId] = useState("");
  const [maskPath, setMaskPath] = useState("");
  const [protectedRegions, setProtectedRegions] = useState("[]");
  const [assetName, setAssetName] = useState("");
  const [purpose, setPurpose] = useState("");
  const [sourceKind, setSourceKind] = useState("");
  const [sourceId, setSourceId] = useState("");
  const [sourceRevision, setSourceRevision] = useState("");
  const [licenseNote, setLicenseNote] = useState("");
  const [sourceNote, setSourceNote] = useState("");
  const [requestedDownstreamProfile, setRequestedDownstreamProfile] = useState<
    "" | NonNullable<AssetMetadata["requested_downstream_profile"]>
  >("");
  const [params, setParams] = useState("{}");
  const [error, setError] = useState<string | null>(null);

  const assetConfig = assetConfigs[assetType];
  const referenceOptions = sortedReferences(references);
  const revisions = referenceOptions.filter((reference) => reference.id === referencePack);
  const usesApprovedBase = approvedBaseWorkflows.includes(workflow);
  const isRegistryReady =
    assets.includes(assetType) && specs.includes(assetConfig.targetSpec) && provider.length > 0;

  useEffect(() => {
    const firstRegisteredAsset = assets.find(isAssetType);
    if (firstRegisteredAsset !== undefined && !assets.includes(assetType)) {
      setAssetType(firstRegisteredAsset);
      setWorkflow(assetConfigs[firstRegisteredAsset].workflows[0]);
    }
  }, [assetType, assets]);

  useEffect(() => {
    if (provider === "" && providers[0]) {
      setProvider(providers[0]);
    }
  }, [provider, providers]);

  useEffect(() => {
    if (selectedReference !== undefined) {
      setReferencePack(selectedReference?.id ?? "");
      setReferenceRevision(selectedReference ? String(selectedReference.revision) : "");
    }
  }, [selectedReference]);

  const handleSubmit = () => {
    const parsedParams = parseParams(params);
    if (parsedParams === null) {
      setError("Parameters must be a JSON object with string, number, or boolean values.");
      return;
    }
    if (!isRegistryReady) {
      setError("The selected asset type, its target spec, and a provider are required.");
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
    const normalizedParent = parentAssetId.trim();
    if (usesApprovedBase && normalizedParent === "") {
      setError("An approved base asset id is required for this workflow.");
      return;
    }

    let metadata: AssetMetadata | null = null;
    if (assetType === "dialogue_background") {
      const requiredMetadata = [
        assetName,
        purpose,
        sourceKind,
        sourceId,
        sourceRevision,
        licenseNote,
        sourceNote,
      ].map((value) => value.trim());
      if (requiredMetadata.some((value) => value === "")) {
        setError("Dialogue background metadata fields are required.");
        return;
      }
      const assetNameError = portableStorageIdError(assetName);
      if (assetNameError !== null) {
        setError(`Asset name ${assetNameError}`);
        return;
      }
      metadata = {
        name: assetName,
        purpose: purpose.trim(),
        source: {
          kind: sourceKind.trim(),
          id: sourceId.trim(),
          revision: sourceRevision.trim(),
        },
        license_note: licenseNote.trim(),
        source_note: sourceNote.trim(),
        requested_downstream_profile:
          requestedDownstreamProfile === "" ? null : requestedDownstreamProfile,
      };
    }

    const sources: SourceSpec[] = [
      textSource.trim() === "" ? null : { kind: "text", ref: textSource.trim() },
      conceptSource.trim() === "" ? null : { kind: "concept_art", ref: conceptSource.trim() },
      approvedAssetSource.trim() === ""
        ? null
        : { kind: assetConfig.approvedSourceKind, ref: approvedAssetSource.trim() },
    ].filter((source): source is SourceSpec => source !== null);

    const edit =
      workflow === "masked_variant"
        ? { mask_path: maskPath.trim(), protected_regions: parsedRegions ?? [] }
        : null;
    setError(null);
    onSubmit({
      version: "1.0",
      asset_type: assetType,
      target_spec: assetConfig.targetSpec,
      workflow,
      provider,
      character_ref_pack: referencePack === "" ? null : referencePack,
      character_ref_pack_rev: revision,
      parent_asset_id: usesApprovedBase ? normalizedParent : null,
      sources,
      edit,
      metadata,
      params: parsedParams,
    });
  };

  return (
    <section aria-label="manifest-controls">
      <h2>Create job</h2>
      <label>
        Asset type
        <select
          value={assetType}
          onChange={(event) => {
            if (isAssetType(event.target.value)) {
              const nextAssetType = event.target.value;
              setAssetType(nextAssetType);
              setWorkflow(assetConfigs[nextAssetType].workflows[0]);
              setApprovedAssetSource("");
              setParentAssetId("");
              setMaskPath("");
              setProtectedRegions("[]");
              setError(null);
            }
          }}
        >
          {assets.filter(isAssetType).map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      </label>
      <label>
        Workflow
        <select
          value={workflow}
          onChange={(event) => {
            if (isWorkflow(event.target.value, assetType)) {
              setWorkflow(event.target.value);
            }
          }}
        >
          {assetConfig.workflows.map((option) => (
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
        Reference pack for new job
        <select
          value={referencePack}
          onChange={(event) => {
            const nextPack = event.target.value;
            const firstRevision = referenceOptions.find((reference) => reference.id === nextPack);
            setReferencePack(nextPack);
            setReferenceRevision(firstRevision ? String(firstRevision.revision) : "");
            onSelectedReferenceChange?.(
              firstRevision ? { id: firstRevision.id, revision: firstRevision.revision } : null,
            );
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
        Reference revision for new job
        <select
          value={referenceRevision}
          disabled={referencePack === ""}
          onChange={(event) => {
            setReferenceRevision(event.target.value);
            const revision = Number(event.target.value);
            if (referencePack !== "" && Number.isInteger(revision)) {
              onSelectedReferenceChange?.({ id: referencePack, revision });
            }
          }}
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
        {assetConfig.approvedSourceLabel}
        <input
          value={approvedAssetSource}
          onChange={(event) => setApprovedAssetSource(event.target.value)}
        />
      </label>
      {usesApprovedBase ? (
        <label>
          Approved base asset id
          <input
            value={parentAssetId}
            required
            onChange={(event) => setParentAssetId(event.target.value)}
          />
        </label>
      ) : null}
      {workflow === "masked_variant" ? (
        <>
          <label>
            Mask path for new job
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
      {assetType === "dialogue_background" ? (
        <fieldset>
          <legend>Dialogue background metadata</legend>
          <label>
            Asset name
            <input value={assetName} onChange={(event) => setAssetName(event.target.value)} />
          </label>
          <label>
            Purpose
            <input value={purpose} onChange={(event) => setPurpose(event.target.value)} />
          </label>
          <label>
            Source kind
            <input value={sourceKind} onChange={(event) => setSourceKind(event.target.value)} />
          </label>
          <label>
            Source id
            <input value={sourceId} onChange={(event) => setSourceId(event.target.value)} />
          </label>
          <label>
            Source revision
            <input
              value={sourceRevision}
              onChange={(event) => setSourceRevision(event.target.value)}
            />
          </label>
          <label>
            License note
            <input value={licenseNote} onChange={(event) => setLicenseNote(event.target.value)} />
          </label>
          <label>
            Source note
            <input value={sourceNote} onChange={(event) => setSourceNote(event.target.value)} />
          </label>
          <label>
            Requested downstream profile
            <select
              value={requestedDownstreamProfile}
              onChange={(event) => {
                const value = event.target.value;
                setRequestedDownstreamProfile(
                  value === "fe8-dialogue-background-feimg2" ? value : "",
                );
              }}
            >
              <option value="">None</option>
              <option value="fe8-dialogue-background-feimg2">
                fe8-dialogue-background-feimg2
              </option>
            </select>
          </label>
        </fieldset>
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
