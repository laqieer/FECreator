import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { JobTimeline } from "./JobTimeline";

test("renders events in order", () => {
  render(
    <JobTimeline
      events={[
        { seq: 0, at: "2026-07-24T00:00:00+00:00", kind: "created", message: "job created" },
        {
          seq: 1,
          at: "2026-07-24T00:00:01+00:00",
          kind: "transition",
          message: "created->planning",
        },
      ]}
    />,
  );
  const items = screen.getAllByRole("listitem");
  expect(items).toHaveLength(2);
  expect(items[0]).toHaveTextContent("created");
});

test("shows disconnected status without inventing success", () => {
  render(<JobTimeline events={[]} connectionState="disconnected" />);
  expect(screen.getByRole("alert")).toHaveTextContent("Timeline disconnected");
  expect(screen.getByText("No job events yet.")).toBeInTheDocument();
});
