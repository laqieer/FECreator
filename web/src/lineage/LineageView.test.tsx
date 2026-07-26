import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { LineageView } from "./LineageView";
import type { LineageNode } from "../api/types";

function node(overrides: Partial<LineageNode>): LineageNode {
  return {
    asset_id: "node-1",
    operation: "create_neutral",
    parents: [],
    provider: null,
    model: null,
    prompt: null,
    reference_pack: null,
    reference_pack_rev: null,
    seed: null,
    params: {},
    mask: null,
    protected_regions: [],
    metrics: {},
    approved_by: null,
    output_hashes: [],
    created_at: "2026-07-24T00:00:00+00:00",
    ...overrides,
  };
}

test("reject fires with asset id", async () => {
  const onReject = vi.fn();
  render(
    <LineageView
      nodes={[node({ asset_id: "a1" })]}
      onApprove={vi.fn()}
      onReject={onReject}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Reject a1" }));
  expect(onReject).toHaveBeenCalledWith("a1");
});

test("shows parent lineage and explicit empty state", () => {
  const { rerender } = render(
    <LineageView
      nodes={[
        node({
          asset_id: "v2",
          operation: "variant_masked_edit",
          parents: ["root", "mask-1"],
        }),
      ]}
      onApprove={vi.fn()}
      onReject={vi.fn()}
    />,
  );
  expect(screen.getByText(/parents: root, mask-1/)).toBeInTheDocument();

  rerender(<LineageView nodes={[]} onApprove={vi.fn()} onReject={vi.fn()} />);
  expect(screen.getByText("No lineage nodes available.")).toBeInTheDocument();
});

test("groups the selected asset, ancestors, and descendants for traversal", () => {
  render(
    <LineageView
      selected={node({ asset_id: "candidate", parents: ["root"] })}
      ancestors={[node({ asset_id: "root" })]}
      descendants={[node({ asset_id: "export", operation: "export_spec", parents: ["candidate"] })]}
    />,
  );

  expect(screen.getByRole("heading", { name: "Selected asset" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Ancestors" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Descendants" })).toBeInTheDocument();
  expect(screen.getByText("export")).toBeInTheDocument();
});

test("keeps traversal data separate from React children", () => {
  // @ts-expect-error LineageView must not accept React children that could clobber data.
  const invalid = <LineageView nodes={[]}>clobbered</LineageView>;
  expect(invalid).toBeTruthy();

  render(<LineageView selected={null} ancestors={[]} descendants={[]} />);
  expect(screen.getByText("No lineage node selected.")).toBeInTheDocument();
});
