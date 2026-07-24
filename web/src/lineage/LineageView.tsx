import type { LineageNode } from "../api/types";

interface LineageViewProps {
  nodes: LineageNode[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

export function LineageView({ nodes, onApprove, onReject }: LineageViewProps) {
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
                <button type="button" onClick={() => onApprove(node.asset_id)}>
                  Approve {node.asset_id}
                </button>
                <button type="button" onClick={() => onReject(node.asset_id)}>
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
