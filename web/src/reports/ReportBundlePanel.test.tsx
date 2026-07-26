import "@testing-library/jest-dom/vitest";
import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ReportBundlePanel } from "./ReportBundlePanel";
import { createStubApiClient, renderWithProviders } from "../test/util";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("loads the sanitized report and revokes the bundle download object URL", async () => {
  const getBundleFile = vi.fn(async () => new Blob(["report"], { type: "application/json" }));
  const createObjectURL = vi.fn(() => "blob:report");
  const revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => undefined);
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
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:report");
});
