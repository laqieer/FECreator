import type { LineageNode } from "../api/types";

interface LineageTraversalProps {
  selected: LineageNode | null;
  ancestors?: LineageNode[];
  descendants?: LineageNode[];
  loading?: boolean;
  error?: string | null;
  children?: never;
}

interface LineageNodesProps {
  nodes: LineageNode[];
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
  children?: never;
}

type LineageViewProps = LineageTraversalProps | LineageNodesProps;

function isNodesMode(props: LineageViewProps): props is LineageNodesProps {
  return "nodes" in props;
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

function LineageNodeList({ nodes, empty }: { nodes: LineageNode[]; empty: string }) {
  if (nodes.length === 0) {
    return <p>{empty}</p>;
  }
  return (
    <ul>
      {nodes.map((node) => (
        <NodeSummary key={node.asset_id} node={node} />
      ))}
    </ul>
  );
}

function LineageNodesView({ nodes, onApprove, onReject }: LineageNodesProps) {
  return (
    <section aria-label="lineage-view">
      <h2>Lineage and variants</h2>
      {nodes.length === 0 ? (
        <p>No lineage nodes available.</p>
      ) : (
        <ul>
          {nodes.map((node) => (
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

export function LineageView(props: LineageViewProps) {
  if (isNodesMode(props)) {
    return <LineageNodesView {...props} />;
  }

  const { selected, ancestors = [], descendants = [], loading = false, error = null } = props;
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
            <ul>
              <NodeSummary node={selected} />
            </ul>
          </section>
          <section>
            <h3>Ancestors</h3>
            <LineageNodeList nodes={ancestors} empty="No ancestors." />
          </section>
          <section>
            <h3>Descendants</h3>
            <LineageNodeList nodes={descendants} empty="No descendants." />
          </section>
        </>
      )}
    </section>
  );
}
