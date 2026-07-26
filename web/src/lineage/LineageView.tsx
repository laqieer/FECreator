import type { LineageNode } from "../api/types";

interface LineageViewProps {
  nodes?: LineageNode[];
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  selected?: LineageNode | null;
  ancestors?: LineageNode[];
  children?: LineageNode[];
  loading?: boolean;
  error?: string | null;
}

function NodeSummary({ node }: { node: LineageNode }) {
  return (
    <li>
      <p>
        <strong>{node.asset_id}</strong> · {node.operation} · parents: {(node.parents ?? []).join(", ") || "none"}
      </p>
    </li>
  );
}

export function LineageView({
  nodes,
  onApprove,
  onReject,
  selected,
  ancestors = [],
  children = [],
  loading = false,
  error = null,
}: LineageViewProps) {
  if (selected !== undefined) {
    return (
      <section aria-label="lineage-view">
        <h2>Lineage and variants</h2>
        {loading ? <p role="status">Loading lineage…</p> : null}
        {error ? <p role="alert">{error}</p> : null}
        {selected === null ? (
          <p>No lineage node selected.</p>
        ) : (
          <>
            <section>
              <h3>Selected asset</h3>
              <ul><NodeSummary node={selected} /></ul>
            </section>
            <section>
              <h3>Ancestors</h3>
              {ancestors.length === 0 ? <p>No ancestors.</p> : <ul>{ancestors.map((node) => <NodeSummary key={node.asset_id} node={node} />)}</ul>}
            </section>
            <section>
              <h3>Children</h3>
              {children.length === 0 ? <p>No children.</p> : <ul>{children.map((node) => <NodeSummary key={node.asset_id} node={node} />)}</ul>}
            </section>
          </>
        )}
      </section>
    );
  }

  const currentNodes = nodes ?? [];
  return (
    <section aria-label="lineage-view">
      <h2>Lineage and variants</h2>
      {currentNodes.length === 0 ? (
        <p>No lineage nodes available.</p>
      ) : (
        <ul>
          {currentNodes.map((node) => (
            <li key={node.asset_id}>
              <p>
                <strong>{node.asset_id}</strong> · {node.operation} · parents: {(node.parents ?? []).join(", ") || "none"}
              </p>
              <div>
                <button type="button" onClick={() => onApprove?.(node.asset_id)}>
                  Approve {node.asset_id}
                </button>
                <button type="button" onClick={() => onReject?.(node.asset_id)}>
                  Reject {node.asset_id}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
