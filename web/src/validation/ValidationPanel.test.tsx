import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ValidationPanel } from "./ValidationPanel";
import { createStubApiClient, renderWithProviders } from "../test/util";

test("validates the selected job and groups diagnostics by severity", async () => {
  const validateJob = vi.fn(async () => [
    { code: "palette", severity: "error" as const, message: "Too many colors." },
    { code: "crop", severity: "warning" as const, message: "Crop is off-center." },
    { code: "info", severity: "info" as const, message: "Ready to export." },
  ]);
  renderWithProviders(
    <ValidationPanel jobId="job-1" targetSpec="fe-gba-portrait-standard" />,
    createStubApiClient({ validateJob }),
  );

  expect(await screen.findByRole("heading", { name: "Errors (1)" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Warnings (1)" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Information (1)" })).toBeInTheDocument();
  expect(screen.getByText("Target: fe-gba-portrait-standard")).toBeInTheDocument();
  expect(validateJob).toHaveBeenCalledWith("job-1");
});
