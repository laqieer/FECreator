import "@testing-library/jest-dom/vitest";
import { act, fireEvent, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ReportBundlePanel } from "./ReportBundlePanel";
import { createStubApiClient, renderWithProviders } from "../test/util";

afterEach(() => {
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function trackAnchorClicks() {
  const clicked: Array<{ anchor: HTMLAnchorElement; connected: boolean; download: string }> = [];
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    clicked.push({ anchor: this, connected: this.isConnected, download: this.download });
  });
  return clicked;
}

test("loads the sanitized report and defers revoking the bundle download object URL", async () => {
  const getBundleFile = vi.fn(async () => new Blob(["report"], { type: "application/json" }));
  const createObjectURL = vi.fn(() => "blob:report");
  const revokeObjectURL = vi.fn();
  trackAnchorClicks();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  renderWithProviders(
    <ReportBundlePanel jobId="job-1" />,
    createStubApiClient({
      getBundleFile,
      listBundleEntries: async () => [{ path: "reports/final report.json", size_bytes: 6 }],
    }),
  );

  expect(await screen.findByText("Report for job-1")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Download final report.json" }));

  expect(getBundleFile).toHaveBeenCalledWith("job-1", "reports/final report.json");
  expect(createObjectURL).toHaveBeenCalled();
  expect(revokeObjectURL).not.toHaveBeenCalled();
});

test("appends the anchor before clicking, removes it, and defers revocation", async () => {
  const createObjectURL = vi.fn(() => "blob:report");
  const revokeObjectURL = vi.fn();
  const clicked = trackAnchorClicks();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  renderWithProviders(
    <ReportBundlePanel jobId="job-1" />,
    createStubApiClient({
      listBundleEntries: async () => [{ path: "reports/final report.json", size_bytes: 6 }],
    }),
  );

  const button = await screen.findByRole("button", { name: "Download final report.json" });
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(button);
  });

  expect(clicked).toHaveLength(1);
  expect(clicked[0]!.connected).toBe(true);
  expect(clicked[0]!.download).toBe("final report.json");
  expect(clicked[0]!.anchor.isConnected).toBe(false);
  expect(revokeObjectURL).not.toHaveBeenCalled();

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });

  expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
});

test("revokes a deferred bundle object URL when the panel unmounts", async () => {
  const createObjectURL = vi.fn(() => "blob:report");
  const revokeObjectURL = vi.fn();
  trackAnchorClicks();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  const view = renderWithProviders(
    <ReportBundlePanel jobId="job-1" />,
    createStubApiClient({
      listBundleEntries: async () => [{ path: "reports/final report.json", size_bytes: 6 }],
    }),
  );

  const button = await screen.findByRole("button", { name: "Download final report.json" });
  vi.useFakeTimers();
  await act(async () => {
    fireEvent.click(button);
  });
  expect(revokeObjectURL).not.toHaveBeenCalled();

  view.unmount();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");

  await act(async () => {
    await vi.advanceTimersByTimeAsync(60_000);
  });
  expect(revokeObjectURL).toHaveBeenCalledTimes(1);
});

test("stays silent when no job is selected", () => {
  renderWithProviders(
    <ReportBundlePanel jobId={null} />,
    createStubApiClient({
      getJobReport: async () => {
        throw new Error("report must not load without a job");
      },
    }),
  );

  expect(screen.queryByRole("status")).not.toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  expect(screen.getByText("Select a job to load its report and bundle.")).toBeInTheDocument();
});
