import { useQuery } from "@tanstack/react-query";
import {
  lazy,
  Suspense,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import type { Manifest, Job, JobState } from "../api/types";
import type { IndexedFrame } from "../palette/framePreview";
import { useApiClient } from "../api/context";
import { clearMask, emptyMask, type MaskGrid } from "../canvas/maskModel";
import { JobTimeline } from "../jobs/JobTimeline";
import { useJobEvents } from "../jobs/useJobEvents";
import { LineageView } from "../lineage/LineageView";
import { PalettePreview } from "../palette/PalettePreview";
import { ReferenceBoard } from "../references/ReferenceBoard";
import { ReviewGallery } from "../review/ReviewGallery";

const LazyMaskEditor = lazy(async () => {
  const module = await import("../canvas/MaskEditor");
  return { default: module.MaskEditor };
});

const tabs = ["Review", "References", "Mask", "Palette", "Timeline", "Lineage"] as const;
const terminalStates: JobState[] = ["completed", "failed", "cancelled"];
const sampleMaskWidth = 96;
const sampleMaskHeight = 80;
const sampleCandidateSrc = "data:image/svg+xml;charset=utf-8,%3Csvg xmlns='http://www.w3.org/2000/svg' width='80' height='48'%3E%3Crect width='80' height='48' fill='%23d9d9d9'/%3E%3C/svg%3E";
const samplePalette: [number, number, number][] = [
  [0, 0, 0],
  [0, 248, 0],
  [80, 96, 200],
  [248, 248, 248],
];
const sampleFrames: IndexedFrame[] = [
  {
    id: "eyes-open",
    label: "Eyes open",
    kind: "eyes",
    width: 4,
    height: 4,
    pixels: [
      [0, 1, 1, 0],
      [0, 3, 3, 0],
      [0, 1, 1, 0],
      [0, 0, 0, 0],
    ],
  },
  {
    id: "mouth-talk",
    label: "Mouth talk",
    kind: "mouth",
    width: 4,
    height: 4,
    pixels: [
      [0, 0, 0, 0],
      [0, 2, 2, 0],
      [0, 3, 3, 0],
      [0, 0, 0, 0],
    ],
  },
];

type TabName = (typeof tabs)[number];
type RegistryQuery = ReturnType<typeof useQuery<string[]>>;

function RegistryStatus({
  query,
  singular,
  plural,
}: {
  query: RegistryQuery;
  singular: string;
  plural: string;
}) {
  if (query.isPending) {
    return <li role="status">Loading {plural}…</li>;
  }

  if (query.isError) {
    return <li role="alert">Unable to load {plural}.</li>;
  }

  const count = query.data.length;
  if (count === 0) {
    return <li>No {plural} available.</li>;
  }

  const label = count === 1 ? singular : plural;
  return <li>{count} {label} available</li>;
}

function buildDefaultManifest(assets: string[], specs: string[], providers: string[]): Manifest | null {
  const [assetType] = assets;
  const [targetSpec] = specs;
  const [provider] = providers;

  if (!assetType || !targetSpec || !provider) {
    return null;
  }

  return {
    version: "1.0",
    asset_type: assetType as Manifest["asset_type"],
    target_spec: targetSpec as Manifest["target_spec"],
    workflow: "text_to_portrait",
    provider,
    character_ref_pack: null,
    character_ref_pack_rev: null,
    sources: [],
    edit: null,
    params: {},
  };
}

function isTerminalState(state: JobState): state is Extract<JobState, "completed" | "failed" | "cancelled"> {
  return terminalStates.includes(state);
}

export function App() {
  const client = useApiClient();
  const [activeTab, setActiveTab] = useState<TabName>("Review");
  const [manifestText, setManifestText] = useState("{}\n");
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [selectedJobId, setSelectedJobId] = useState("");
  const [jobIdInput, setJobIdInput] = useState("");
  const [jobAction, setJobAction] = useState<"idle" | "creating" | "loading">("idle");
  const [jobError, setJobError] = useState<string | null>(null);
  const [maskHistory, setMaskHistory] = useState<MaskGrid[]>(() => [emptyMask(sampleMaskWidth, sampleMaskHeight)]);
  const [selectedFrameId, setSelectedFrameId] = useState(sampleFrames[0]?.id ?? "");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: () => client.listAssets() });
  const specsQuery = useQuery({ queryKey: ["specs"], queryFn: () => client.listSpecs() });
  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: () => client.listProviders(),
  });
  const jobEvents = useJobEvents(selectedJobId);

  const assetOptions = assetsQuery.data ?? [];
  const specOptions = specsQuery.data ?? [];
  const providerOptions = providersQuery.data ?? [];
  const defaultManifest = buildDefaultManifest(assetOptions, specOptions, providerOptions);
  const selectedTerminalState = selectedJob && isTerminalState(selectedJob.state) ? selectedJob.state : null;
  const currentMask = maskHistory[maskHistory.length - 1] ?? emptyMask(sampleMaskWidth, sampleMaskHeight);

  const selectTab = (index: number) => {
    setActiveTab(tabs[index]);
    tabRefs.current[index]?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectTab((index + 1) % tabs.length);
      return;
    }

    if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectTab((index - 1 + tabs.length) % tabs.length);
      return;
    }

    if (event.key === "Home") {
      event.preventDefault();
      selectTab(0);
      return;
    }

    if (event.key === "End") {
      event.preventDefault();
      selectTab(tabs.length - 1);
    }
  };

  const handleCreateJob = async () => {
    if (!defaultManifest) {
      setJobError("Unable to create a timeline job from empty registries.");
      return;
    }

    setJobAction("creating");
    setJobError(null);
    try {
      const job = await client.createJob(defaultManifest);
      setSelectedJob(job);
      setSelectedJobId(job.id);
      setJobIdInput(job.id);
    } catch {
      setSelectedJob(null);
      setSelectedJobId("");
      setJobError("Unable to create a timeline job.");
    } finally {
      setJobAction("idle");
    }
  };

  const handleLoadJob = async () => {
    const normalizedJobId = jobIdInput.trim();
    if (!normalizedJobId) {
      setJobError("Enter a job ID to load.");
      return;
    }

    setJobAction("loading");
    setJobError(null);
    try {
      const job = await client.getJob(normalizedJobId);
      setSelectedJob(job);
      setSelectedJobId(job.id);
      setJobIdInput(job.id);
    } catch {
      setSelectedJob(null);
      setSelectedJobId("");
      setJobError(`Unable to load job ${normalizedJobId}.`);
    } finally {
      setJobAction("idle");
    }
  };

  const handleMaskChange = (nextMask: MaskGrid) => {
    setMaskHistory((history) => [...history, nextMask]);
  };

  const handleMaskClear = () => {
    setMaskHistory((history) => [...history, clearMask(history[history.length - 1] ?? currentMask)]);
  };

  const handleMaskUndo = () => {
    setMaskHistory((history) => (history.length > 1 ? history.slice(0, -1) : history));
  };

  return (
    <div>
      <header>
        <h1>FECreator</h1>
        <p>Local-first portrait review and tuning workbench.</p>
        <section aria-label="registry-status">
          <h2>Registry status</h2>
          <ul>
            <RegistryStatus query={assetsQuery} singular="asset type" plural="asset types" />
            <RegistryStatus query={specsQuery} singular="spec" plural="specs" />
            <RegistryStatus query={providersQuery} singular="provider" plural="providers" />
          </ul>
        </section>
      </header>
      <nav aria-label="Workbench sections">
        <div role="tablist" aria-label="Workbench sections">
          {tabs.map((tab, index) => {
            const selected = activeTab === tab;
            const tabId = `${tab.toLowerCase()}-tab`;
            const panelId = `${tab.toLowerCase()}-panel`;
            return (
              <button
                key={tab}
                ref={(element) => {
                  tabRefs.current[index] = element;
                }}
                id={tabId}
                role="tab"
                type="button"
                tabIndex={selected ? 0 : -1}
                aria-selected={selected}
                aria-controls={panelId}
                onClick={() => setActiveTab(tab)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                {tab}
              </button>
            );
          })}
        </div>
      </nav>
      <main id={`${activeTab.toLowerCase()}-panel`} role="tabpanel" tabIndex={0} aria-labelledby={`${activeTab.toLowerCase()}-tab`}>
        {activeTab === "Review" ? (
          <ReviewGallery
            candidates={[
              {
                id: "c1",
                src: sampleCandidateSrc,
                imageWidth: 80,
                imageHeight: 48,
                cropRect: { x: -10, y: 8, w: 50, h: 24 },
                specRect: { x: 20, y: 4, w: 24, h: 24 },
              },
            ]}
            onApprove={() => undefined}
            onReject={() => undefined}
          />
        ) : null}
        {activeTab === "References" ? (
          <ReferenceBoard swatches={["#00f800", "#5060c8"]} manifestText={manifestText} onManifestChange={setManifestText} />
        ) : null}
        {activeTab === "Mask" ? (
          <Suspense fallback={<p role="status">Loading mask editor…</p>}>
            <LazyMaskEditor
              width={sampleMaskWidth}
              height={sampleMaskHeight}
              mask={currentMask}
              protectedRegions={[{ x: 12, y: 10, w: 16, h: 12, label: "face" }]}
              onChange={handleMaskChange}
              onClear={handleMaskClear}
              onUndo={handleMaskUndo}
              canUndo={maskHistory.length > 1}
            />
          </Suspense>
        ) : null}
        {activeTab === "Palette" ? (
          <PalettePreview
            palette={samplePalette}
            frames={sampleFrames}
            selectedFrameId={selectedFrameId}
            onSelectFrame={setSelectedFrameId}
            scale={8}
          />
        ) : null}
        {activeTab === "Timeline" ? (
          <section aria-label="timeline-workbench">
            <h2>Job timeline</h2>
            <div>
              <button type="button" onClick={handleCreateJob} disabled={jobAction !== "idle" || defaultManifest === null}>
                Create timeline job
              </button>
              <label>
                Job ID
                <input value={jobIdInput} onChange={(event) => setJobIdInput(event.target.value)} />
              </label>
              <button type="button" onClick={handleLoadJob} disabled={jobAction !== "idle"}>
                Load job
              </button>
            </div>
            {jobAction === "creating" ? <p role="status">Creating job…</p> : null}
            {jobAction === "loading" ? <p role="status">Loading job…</p> : null}
            {jobError ? <p role="alert">{jobError}</p> : null}
            {selectedJob ? <p role="status">Selected job {selectedJob.id} is {selectedJob.state}.</p> : null}
            {selectedJobId ? (
              <JobTimeline
                events={jobEvents.events}
                connectionState={jobEvents.connectionState}
                errorMessage={jobEvents.error}
                terminalState={selectedTerminalState}
              />
            ) : (
              <p>Create or load a job to review timeline events.</p>
            )}
          </section>
        ) : null}
        {activeTab === "Lineage" ? <LineageView nodes={[]} onApprove={() => undefined} onReject={() => undefined} /> : null}
      </main>
    </div>
  );
}
