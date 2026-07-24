import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useApiClient } from "../api/context";
import { JobTimeline } from "../jobs/JobTimeline";
import { ReferenceBoard } from "../references/ReferenceBoard";
import { ReviewGallery } from "../review/ReviewGallery";

const tabs = ["Review", "References", "Mask", "Palette", "Timeline", "Lineage"] as const;

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
    return <li>Loading {plural}…</li>;
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

function ActiveView({ tab }: { tab: TabName }) {
  const [manifestText, setManifestText] = useState("{}\n");

  if (tab === "Review") {
    return <ReviewGallery candidates={[]} onApprove={() => undefined} onReject={() => undefined} />;
  }

  if (tab === "References") {
    return <ReferenceBoard swatches={[]} manifestText={manifestText} onManifestChange={setManifestText} />;
  }

  if (tab === "Timeline") {
    return <JobTimeline events={[]} connectionState="idle" />;
  }

  return <p>{tab} workbench panel</p>;
}

export function App() {
  const client = useApiClient();
  const [activeTab, setActiveTab] = useState<TabName>("Review");
  const assetsQuery = useQuery({ queryKey: ["assets"], queryFn: () => client.listAssets() });
  const specsQuery = useQuery({ queryKey: ["specs"], queryFn: () => client.listSpecs() });
  const providersQuery = useQuery({
    queryKey: ["providers"],
    queryFn: () => client.listProviders(),
  });

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
          {tabs.map((tab) => {
            const selected = activeTab === tab;
            const tabId = `${tab.toLowerCase()}-tab`;
            const panelId = `${tab.toLowerCase()}-panel`;
            return (
              <button
                key={tab}
                id={tabId}
                role="tab"
                type="button"
                aria-selected={selected}
                aria-controls={panelId}
                onClick={() => setActiveTab(tab)}
              >
                {tab}
              </button>
            );
          })}
        </div>
      </nav>
      <main id={`${activeTab.toLowerCase()}-panel`} role="tabpanel" aria-labelledby={`${activeTab.toLowerCase()}-tab`}>
        <ActiveView tab={activeTab} />
      </main>
    </div>
  );
}
