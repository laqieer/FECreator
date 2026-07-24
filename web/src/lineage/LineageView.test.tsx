import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { LineageView } from "./LineageView";

test("reject fires with asset id", async () => {
  const onReject = vi.fn();
  render(
    <LineageView
      nodes={[
        {
          asset_id: "a1",
          operation: "create_neutral",
          parents: [],
          created_at: "2026-07-24T00:00:00+00:00",
        },
      ]}
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
        {
          asset_id: "v2",
          operation: "variant_masked_edit",
          parents: ["root", "mask-1"],
          created_at: "2026-07-24T00:00:00+00:00",
        },
      ]}
      onApprove={vi.fn()}
      onReject={vi.fn()}
    />,
  );
  expect(screen.getByText(/parents: root, mask-1/)).toBeInTheDocument();

  rerender(<LineageView nodes={[]} onApprove={vi.fn()} onReject={vi.fn()} />);
  expect(screen.getByText("No lineage nodes available.")).toBeInTheDocument();
});
