import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { SourceStatus } from "./SourceStatus";
import type { SourcePlan } from "../api/types";

const plan: SourcePlan = {
  prompts: ["neutral portrait"],
  reference_roles: {},
  expected_filenames: ["neutral.png"],
  required_expressions: ["neutral"],
  background_contract: "transparent",
  forbidden_colors: [],
  submission_schema: {
    forbidden_changes: [],
    canonical_swatches: [],
    traits: {},
    provenance: "",
    rights: "",
    files: "PNG",
  },
};

test("plans sources and submits selected local files", async () => {
  const onPlan = vi.fn();
  const onSubmit = vi.fn();
  const user = userEvent.setup();
  render(
    <SourceStatus
      jobId="job-1"
      plan={plan}
      loading={false}
      error={null}
      onPlan={onPlan}
      onSubmit={onSubmit}
    />,
  );

  await user.click(screen.getByRole("button", { name: "Plan sources" }));
  await user.upload(screen.getByLabelText("Source files"), new File(["image"], "neutral.png"));
  await user.click(screen.getByRole("button", { name: "Submit sources" }));

  expect(onPlan).toHaveBeenCalledOnce();
  expect(onSubmit).toHaveBeenCalledWith([expect.objectContaining({ name: "neutral.png" })]);
});

test("explains why source actions are unavailable without a job", () => {
  render(
    <SourceStatus
      jobId={null}
      plan={null}
      loading={false}
      error={null}
      onPlan={() => undefined}
      onSubmit={() => undefined}
    />,
  );
  expect(screen.getByText("Create or select a job to plan sources.")).toBeInTheDocument();
});

test("clears selected source files when the selected job changes", async () => {
  const user = userEvent.setup();
  const { rerender } = render(
    <SourceStatus
      jobId="job-a"
      plan={plan}
      loading={false}
      error={null}
      onPlan={() => undefined}
      onSubmit={() => undefined}
    />,
  );

  await user.upload(screen.getByLabelText("Source files"), new File(["image"], "job-a.png"));
  expect(screen.getByRole("button", { name: "Submit sources" })).toBeEnabled();

  rerender(
    <SourceStatus
      jobId="job-b"
      plan={plan}
      loading={false}
      error={null}
      onPlan={() => undefined}
      onSubmit={() => undefined}
    />,
  );

  expect(screen.getByRole("button", { name: "Submit sources" })).toBeDisabled();
});
