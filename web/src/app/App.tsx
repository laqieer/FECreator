import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { JobState, ReferencePack } from "../api/types";
import type { IndexedFrame } from "../palette/framePreview";
import { useApiClient } from "../api/context";
import { clearMask, emptyMask, type MaskGrid } from "../canvas/maskModel";
import { ManifestControls } from "../controls/ManifestControls";
import { SourceStatus } from "../controls/SourceStatus";
import { JobQueue } from "../dashboard/JobQueue";
import { JobTimeline } from "../jobs/JobTimeline";
import { useJobEventSource } from "../jobs/eventSourceContext";
import { LineageView } from "../lineage/LineageView";
import { PalettePreview } from "../palette/PalettePreview";
import { ReferenceBoard } from "../references/ReferenceBoard";
import { ReviewGallery } from "../review/ReviewGallery";
import { useCandidateArtifactUrls } from "../review/useCandidateArtifactUrls";
import { useWorkbench } from "../workbench/useWorkbench";

const LazyMaskEditor = lazy(async () => {
  const module = await import("../canvas/MaskEditor");
  return { default: module.MaskEditor };
});

const tabs = ["Review", "References", "Mask", "Palette", "Timeline", "Lineage"] as const;
const terminalStates: JobState[] = ["completed", "failed", "cancelled"];
const sampleMaskWidth = 96;
const sampleMaskHeight = 80;
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
  return <li>{count} {count === 1 ? singular : plural} available</li>;
}

function isTerminalState(state: JobState): state is Extract<JobState, "completed" | "failed" | "cancelled"> {
  return terminalStates.includes(state);
}

export function App() {
  const client = useApiClient();
  const eventSource = useJobEventSource();
  const workbench = useWorkbench(client, eventSource);
  const reviewArtifacts = useCandidateArtifactUrls(
    client,
    workbench.selectedJobId,
    workbench.candidate,
  );
  const [activeTab, setActiveTab] = useState<TabName>("Review");
  const [manifestText, setManifestText] = useState("{}\n");
  const [maskHistory, setMaskHistory] = useState<MaskGrid[]>(() => [
    emptyMask(sampleMaskWidth, sampleMaskHeight),
  ]);
  const [selectedFrameId, setSelectedFrameId] = useState(sampleFrames[0]?.id ?? "");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: () => client.listAssets() });
  const specsQuery = useQuery({ queryKey: ["specs"], queryFn: () => client.listSpecs() });
  const providersQuery = useQuery({ queryKey: ["providers"], queryFn: () => client.listProviders() });
  const referencePacksQuery = useQuery({
    queryKey: ["reference-packs"],
    queryFn: () => client.listReferencePacks(),
  });
  const referenceIds = referencePacksQuery.data ?? [];
  const referenceHistoryQuery = useQuery({
    queryKey: ["reference-history", referenceIds],
    enabled: referencePacksQuery.isSuccess,
    queryFn: async (): Promise<ReferencePack[]> =>
      (await Promise.all(referenceIds.map((id) => client.listReferenceHistory(id)))).flat(),
  });

  useEffect(() => {
    if (workbench.selectedJob !== null) {
      setManifestText(JSON.stringify(workbench.selectedJob.manifest, null, 2));
    }
  }, [workbench.selectedJob]);

  const currentMask =
    maskHistory[maskHistory.length - 1] ?? emptyMask(sampleMaskWidth, sampleMaskHeight);
  const selectedTerminalState =
    workbench.selectedJob && isTerminalState(workbench.selectedJob.state)
      ? workbench.selectedJob.state
      : null;
  const selectedReference = referenceHistoryQuery.data?.find(
    (reference) =>
      reference.id === workbench.selectedJob?.manifest.character_ref_pack &&
      reference.revision === workbench.selectedJob?.manifest.character_ref_pack_rev,
  );

  const selectTab = (index: number) => {
    setActiveTab(tabs[index]);
    tabRefs.current[index]?.focus();
  };

  const handleTabKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectTab((index + 1) % tabs.length);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectTab((index - 1 + tabs.length) % tabs.length);
    } else if (event.key === "Home") {
      event.preventDefault();
      selectTab(0);
    } else if (event.key === "End") {
      event.preventDefault();
      selectTab(tabs.length - 1);
    }
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
      <section aria-label="job-workbench">
        <JobQueue
          jobs={workbench.jobs}
          selectedJobId={workbench.selectedJobId}
          loading={workbench.action === "loading" && workbench.jobs.length === 0}
          error={workbench.error}
          onSelect={workbench.selectJob}
        />
        <ManifestControls
          assets={assetsQuery.data ?? []}
          specs={specsQuery.data ?? []}
          providers={providersQuery.data ?? []}
          references={referenceHistoryQuery.data ?? []}
          submitting={workbench.action === "creating"}
          onSubmit={workbench.createJob}
        />
        <SourceStatus
          jobId={workbench.selectedJobId}
          plan={workbench.sourcePlan}
          loading={
            workbench.action === "planning-sources" || workbench.action === "submitting-sources"
          }
          error={workbench.sourceError}
          onPlan={workbench.planSources}
          onSubmit={workbench.submitSources}
        />
        {workbench.selectedJob ? (
          <p role="status">
            Selected job {workbench.selectedJob.id} is {workbench.selectedJob.state}.
          </p>
        ) : null}
      </section>
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
      <main
        id={`${activeTab.toLowerCase()}-panel`}
        role="tabpanel"
        tabIndex={0}
        aria-labelledby={`${activeTab.toLowerCase()}-tab`}
      >
        {activeTab === "Review" ? (
          <>
            {reviewArtifacts.loading ? <p role="status">Loading review images…</p> : null}
            {reviewArtifacts.error ? <p role="alert">{reviewArtifacts.error}</p> : null}
            <ReviewGallery
              candidates={reviewArtifacts.artifacts.map((artifact) => ({
                id: artifact.path,
                src: artifact.url,
                imageWidth: 128,
                imageHeight: 112,
                cropRect: { x: 0, y: 0, w: 128, h: 112 },
                specRect: { x: 0, y: 0, w: 128, h: 112 },
              }))}
              onApprove={() => undefined}
              onReject={() => undefined}
            />
          </>
        ) : null}
        {activeTab === "References" ? (
          <ReferenceBoard
            swatches={selectedReference?.swatches ?? []}
            manifestText={manifestText}
            onManifestChange={setManifestText}
          />
        ) : null}
        {activeTab === "Mask" ? (
          <Suspense fallback={<p role="status">Loading mask editor…</p>}>
            <LazyMaskEditor
              width={sampleMaskWidth}
              height={sampleMaskHeight}
              mask={currentMask}
              protectedRegions={workbench.selectedJob?.manifest.edit?.protected_regions ?? []}
              onChange={(nextMask) => setMaskHistory((history) => [...history, nextMask])}
              onClear={() =>
                setMaskHistory((history) => [
                  ...history,
                  clearMask(history[history.length - 1] ?? currentMask),
                ])
              }
              onUndo={() =>
                setMaskHistory((history) => (history.length > 1 ? history.slice(0, -1) : history))
              }
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
            {workbench.selectedJobId ? (
              <JobTimeline
                events={workbench.events.events}
                connectionState={workbench.events.connectionState}
                errorMessage={workbench.events.error}
                terminalState={selectedTerminalState}
              />
            ) : (
              <p>Create or select a job to review timeline events.</p>
            )}
          </section>
        ) : null}
        {activeTab === "Lineage" ? (
          <LineageView nodes={[]} onApprove={() => undefined} onReject={() => undefined} />
        ) : null}
      </main>
    </div>
  );
}
