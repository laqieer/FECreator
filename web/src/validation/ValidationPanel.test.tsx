import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ValidationPanel } from "./ValidationPanel";
import { ApiError } from "../api/client";
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

test("stays silent when no job is selected", () => {
  renderWithProviders(
    <ValidationPanel jobId={null} targetSpec={null} />,
    createStubApiClient({
      validateJob: async () => {
        throw new Error("validation must not run without a job");
      },
    }),
  );

  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Select a job to validate.")).toBeInTheDocument();
});

test("surfaces structured diagnostics from a failed validation request", async () => {
  const diagnostics = [
    {
      code: "PALETTE_TOO_MANY_COLORS",
      severity: "error" as const,
      message: "package uses 17 colors",
    },
  ];
  const validateJob = vi.fn(async () => {
    throw new ApiError("POST", "/api/jobs/job-1/validate", 409, diagnostics, diagnostics);
  });
  renderWithProviders(
    <ValidationPanel jobId="job-1" targetSpec="fe-gba-portrait-standard" />,
    createStubApiClient({ validateJob }),
  );

  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("PALETTE_TOO_MANY_COLORS");
  expect(alert).toHaveTextContent("package uses 17 colors");
});

test("reports the transport failure message when no diagnostics are returned", async () => {
  const validateJob = vi.fn(async () => {
    throw new Error("validation service unavailable");
  });
  renderWithProviders(
    <ValidationPanel jobId="job-1" targetSpec="fe-gba-portrait-standard" />,
    createStubApiClient({ validateJob }),
  );

  expect(await screen.findByRole("alert")).toHaveTextContent("validation service unavailable");
});

test("does not repeat the validation request when the window regains focus", async () => {
  const validateJob = vi.fn(async () => []);
  renderWithProviders(
    <ValidationPanel jobId="job-1" targetSpec="fe-gba-portrait-standard" />,
    createStubApiClient({ validateJob }),
  );

  await waitFor(() => expect(validateJob).toHaveBeenCalledTimes(1));
  document.dispatchEvent(new Event("visibilitychange"));
  window.dispatchEvent(new Event("focus"));
  await new Promise((resolve) => setTimeout(resolve, 20));

  expect(validateJob).toHaveBeenCalledTimes(1);
});
