import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ReviewGallery, type ReviewCandidate } from "./ReviewGallery";

const candidate: ReviewCandidate = {
  id: "c1",
  src: "a.png",
  imageWidth: 80,
  imageHeight: 48,
  cropRect: { x: 0, y: 0, w: 80, h: 48 },
  specRect: { x: 0, y: 0, w: 80, h: 48 },
};

test("renders clipped crop and spec overlays from numeric rect props", async () => {
  const onApprove = vi.fn();
  render(
    <ReviewGallery
      candidates={[
        {
          id: "c1",
          src: "a.png",
          imageWidth: 80,
          imageHeight: 48,
          cropRect: { x: -10, y: 8, w: 50, h: 24 },
          specRect: { x: 20, y: 4, w: 24, h: 24 },
        },
      ]}
      onApprove={onApprove}
      onReject={vi.fn()}
    />,
  );

  expect(screen.getByLabelText("crop-overlay-c1")).toHaveStyle({
    left: "0%",
    top: "16.666666666666664%",
    width: "50%",
    height: "50%",
  });
  expect(screen.getByLabelText("spec-overlay-c1")).toHaveStyle({
    left: "25%",
    top: "8.333333333333332%",
    width: "30%",
    height: "50%",
  });
  await userEvent.click(screen.getByRole("button", { name: "Approve c1" }));
  expect(onApprove).toHaveBeenCalledWith("c1");
});

test("shows an explicit empty state when no candidates are available", () => {
  render(<ReviewGallery candidates={[]} onApprove={vi.fn()} onReject={vi.fn()} />);
  expect(screen.getByText("No review candidates available.")).toBeInTheDocument();
});

test("requires a rejection reason and exposes persisted review action status", async () => {
  const onReject = vi.fn();
  const onFinalize = vi.fn();
  const onRetry = vi.fn();
  render(
    <ReviewGallery
      candidates={[
        {
          id: "c1",
          src: "a.png",
          imageWidth: 80,
          imageHeight: 48,
          cropRect: { x: 0, y: 0, w: 80, h: 48 },
          specRect: { x: 0, y: 0, w: 80, h: 48 },
        },
      ]}
      onApprove={vi.fn()}
      onReject={onReject}
      onFinalize={onFinalize}
      onRetry={onRetry}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Reject c1" }));
  expect(screen.getByRole("alert")).toHaveTextContent("A rejection reason is required.");
  expect(onReject).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Finalize review" }));
  await userEvent.click(screen.getByRole("button", { name: "Retry job" }));
  expect(onFinalize).toHaveBeenCalled();
  expect(onRetry).toHaveBeenCalled();
});

test("clears a stale rejection message when the reason changes and before approving", async () => {
  const user = userEvent.setup();
  render(
    <ReviewGallery candidates={[candidate]} onApprove={vi.fn()} onReject={vi.fn()} />,
  );

  await user.click(screen.getByRole("button", { name: "Reject c1" }));
  expect(screen.getByRole("alert")).toHaveTextContent("A rejection reason is required.");

  await user.type(screen.getByLabelText("Rejection reason for c1"), "b");
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();

  await user.clear(screen.getByLabelText("Rejection reason for c1"));
  await user.click(screen.getByRole("button", { name: "Reject c1" }));
  expect(screen.getByRole("alert")).toHaveTextContent("A rejection reason is required.");

  await user.click(screen.getByRole("button", { name: "Approve c1" }));
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("prefers a newer backend action error over a stale rejection message", async () => {
  const user = userEvent.setup();
  const { rerender } = render(
    <ReviewGallery candidates={[candidate]} onApprove={vi.fn()} onReject={vi.fn()} />,
  );

  await user.click(screen.getByRole("button", { name: "Reject c1" }));
  expect(screen.getByRole("alert")).toHaveTextContent("A rejection reason is required.");

  rerender(
    <ReviewGallery
      candidates={[candidate]}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      error="approval unavailable"
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("approval unavailable");
  expect(screen.queryByText("A rejection reason is required.")).not.toBeInTheDocument();
});

test("surfaces an approval history failure instead of empty review history", () => {
  render(
    <ReviewGallery
      candidates={[candidate]}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      approvals={null}
      approvalsError="approval store is locked"
    />,
  );

  expect(screen.getByRole("alert")).toHaveTextContent("approval store is locked");
  expect(screen.queryByText(/Latest review/)).not.toBeInTheDocument();
  expect(screen.queryByText("No review decisions recorded.")).not.toBeInTheDocument();
});

test("reports an empty review history only once approvals loaded", () => {
  render(
    <ReviewGallery candidates={[candidate]} onApprove={vi.fn()} onReject={vi.fn()} approvals={[]} />,
  );

  expect(screen.getByText("No review decisions recorded.")).toBeInTheDocument();
});

test("disables every review control while an action is pending", () => {
  render(
    <ReviewGallery
      candidates={[candidate]}
      onApprove={vi.fn()}
      onReject={vi.fn()}
      onFinalize={vi.fn()}
      onRetry={vi.fn()}
      pendingAction="approve"
    />,
  );

  expect(screen.getByRole("button", { name: "Approve c1" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reject c1" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Finalize review" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Retry job" })).toBeDisabled();
  expect(screen.getByRole("status")).toHaveTextContent("Review action in progress: approve.");
});
