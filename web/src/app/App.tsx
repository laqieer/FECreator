import { useQuery } from "@tanstack/react-query";
import { lazy, Suspense, useEffect, useRef, useState, type KeyboardEvent } from "react";
import type { EditSpec, JobState, ReferencePack } from "../api/types";
import { useApiClient } from "../api/context";
import { clearMask, emptyMask, type MaskGrid } from "../canvas/maskModel";
import { ManifestControls } from "../controls/ManifestControls";
import { SourceStatus } from "../controls/SourceStatus";
import { JobQueue } from "../dashboard/JobQueue";
import { JobTimeline } from "../jobs/JobTimeline";
import { useJobEventSource } from "../jobs/eventSourceContext";
import { LineageView } from "../lineage/LineageView";
import { useLineage } from "../lineage/useLineage";
import { PalettePreview } from "../palette/PalettePreview";
import { ReferenceBoard, type ReferenceSelection } from "../references/ReferenceBoard";
import { ReportBundlePanel } from "../reports/ReportBundlePanel";
import { ReviewGallery } from "../review/ReviewGallery";
import { useCandidateArtifactUrls } from "../review/useCandidateArtifactUrls";
import { ValidationPanel } from "../validation/ValidationPanel";
import { useWorkbench } from "../workbench/useWorkbench";

const LazyMaskEditor = lazy(async () => {
  const module = await import("../canvas/MaskEditor");
  return { default: module.MaskEditor };
});

const tabs = [
  "Review",
  "References",
  "Mask",
  "Palette",
  "Timeline",
  "Lineage",
  "Validation",
  "Report",
] as const;
const terminalStates: JobState[] = ["completed", "failed", "cancelled"];
const sampleMaskWidth = 96;
const sampleMaskHeight = 80;

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
  const [referenceSelection, setReferenceSelection] = useState<ReferenceSelection | null>(null);
  const [maskDraft, setMaskDraft] = useState<EditSpec | null>(null);
  const [maskHistory, setMaskHistory] = useState<MaskGrid[]>(() => [
    emptyMask(sampleMaskWidth, sampleMaskHeight),
  ]);
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
  const lineage = useLineage(
    client,
    workbench.candidate?.lineage_id ?? null,
    workbench.selectedJob?.revision ?? 0,
  );

  useEffect(() => {
    if (workbench.selectedJob !== null) {
      setManifestText(JSON.stringify(workbench.selectedJob.manifest, null, 2));
      setMaskDraft(workbench.selectedJob.manifest.edit);
      if (
        workbench.selectedJob.manifest.character_ref_pack !== null &&
        workbench.selectedJob.manifest.character_ref_pack_rev !== null
      ) {
        setReferenceSelection({
          id: workbench.selectedJob.manifest.character_ref_pack,
          revision: workbench.selectedJob.manifest.character_ref_pack_rev,
        });
      } else {
        setReferenceSelection(null);
      }
    }
  }, [workbench.selectedJob]);

  const currentMask =
    maskHistory[maskHistory.length - 1] ?? emptyMask(sampleMaskWidth, sampleMaskHeight);
  const selectedTerminalState =
    workbench.selectedJob && isTerminalState(workbench.selectedJob.state)
      ? workbench.selectedJob.state
      : null;
  const displayedMaskPath =
    maskDraft?.mask_path ?? workbench.selectedJob?.manifest.edit?.mask_path ?? "masks/draft.png";
  const displayedProtectedRegions =
    maskDraft?.protected_regions ?? workbench.selectedJob?.manifest.edit?.protected_regions ?? [];
  const pendingReviewAction =
    workbench.action === "approving"
      ? "approve"
      : workbench.action === "rejecting"
        ? "reject"
        : workbench.action === "finalizing"
          ? "finalize"
          : workbench.action === "retrying"
            ? "retry"
            : null;

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
          selectedReference={referenceSelection}
          onSelectedReferenceChange={setReferenceSelection}
          submitting={workbench.action === "creating"}
          onSubmit={(manifest) =>
            workbench.createJob(
              manifest.workflow === "masked_variant" && maskDraft !== null
                ? { ...manifest, edit: maskDraft }
                : manifest,
            )
          }
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
              onApprove={() => workbench.approveReview("local-user")}
              onReject={(_candidateId, reason) => workbench.rejectReview("local-user", reason)}
              onFinalize={workbench.finalizeJob}
              onRetry={() => workbench.retryJob("local-user")}
              approvals={workbench.approvals}
              pendingAction={pendingReviewAction}
              error={workbench.actionError}
            />
          </>
        ) : null}
        {activeTab === "References" ? (
          <ReferenceBoard
            references={referenceHistoryQuery.data ?? []}
            selectedReference={referenceSelection}
            onSelectReference={setReferenceSelection}
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
              maskPath={displayedMaskPath}
              protectedRegions={displayedProtectedRegions}
              onDraftChange={setMaskDraft}
              onProtectedRegionsChange={(protectedRegions) =>
                setMaskDraft({ mask_path: displayedMaskPath, protected_regions: protectedRegions })
              }
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
            artifacts={reviewArtifacts.artifacts}
            palette={reviewArtifacts.palette}
            scale={1}
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
          <LineageView
            selected={workbench.candidate ? lineage.data?.selected ?? null : null}
            ancestors={lineage.data?.ancestors ?? []}
            children={lineage.data?.children ?? []}
            loading={lineage.isPending}
            error={lineage.isError ? "Unable to load lineage." : null}
          />
        ) : null}
        {activeTab === "Validation" ? (
          <ValidationPanel
            jobId={workbench.selectedJobId}
            targetSpec={workbench.selectedJob?.manifest.target_spec ?? null}
            refreshKey={workbench.selectedJob?.revision ?? 0}
          />
        ) : null}
        {activeTab === "Report" ? (
          <ReportBundlePanel
            jobId={workbench.selectedJobId}
            refreshKey={workbench.selectedJob?.revision ?? 0}
          />
        ) : null}
      </main>
    </div>
  );
}
