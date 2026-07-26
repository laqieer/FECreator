import { expect, test, type Locator, type Page } from "@playwright/test";
import { buildCandidate } from "./env";

test.describe.configure({ mode: "serial" });

const reviewer = "local-user";

function selectionStatus(page: Page): Locator {
  return page.locator('p[role="status"]', { hasText: /^Selected job / });
}

async function selectedJobId(page: Page): Promise<string> {
  const text = await selectionStatus(page).innerText();
  const match = /^Selected job (\S+) is/.exec(text);
  expect(match, `unexpected selection status: ${text}`).not.toBeNull();
  return match![1]!;
}

async function createJob(page: Page, textSource: string): Promise<string> {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "FECreator", level: 1 })).toBeVisible();
  await expect(page.getByRole("note", { name: "Demo mode notice" })).toHaveCount(0);
  await expect(page.getByLabel(/^Provider/)).toBeVisible();

  await page.getByLabel(/^Provider/).selectOption("fake");
  await page.getByLabel(/^Text source/).fill(textSource);
  await page.getByRole("button", { name: "Create job", exact: true }).click();

  await expect(selectionStatus(page)).toHaveText(/is created\.$/);
  return selectedJobId(page);
}

async function openJob(page: Page, jobId: string, state: string): Promise<void> {
  await page.reload();
  const queued = page.getByRole("button", { name: `${jobId} — ${state}` });
  await expect(queued).toBeVisible();
  await queued.click();
  await expect(queued).toHaveAttribute("aria-pressed", "true");
  await expect(selectionStatus(page)).toHaveText(`Selected job ${jobId} is ${state}.`);
}

function openTab(page: Page, name: string): Promise<void> {
  return page.getByRole("tab", { name, exact: true }).click();
}

test("approves, finalizes, validates, and inspects a local portrait job", async ({ page }) => {
  const jobId = await createJob(page, "a brave knight, neutral expression");

  await page.getByRole("button", { name: "Plan sources", exact: true }).click();
  await expect(page.getByRole("list", { name: "source-prompts" })).toBeVisible();

  buildCandidate(jobId);
  await openJob(page, jobId, "waiting_for_review");

  const approve = page.getByRole("button", { name: "Approve candidate/package/hero.png" });
  await expect(approve).toBeVisible();
  await expect(page.getByRole("img", { name: "Candidate candidate/package/hero.png" })).toBeVisible();
  await expect(page.getByText("No review decisions recorded.")).toBeVisible();

  await approve.click();
  await expect(page.getByText(`Latest review: approved by ${reviewer}.`)).toBeVisible();

  await page.getByRole("button", { name: "Finalize review", exact: true }).click();
  await expect(selectionStatus(page)).toHaveText(`Selected job ${jobId} is completed.`);

  await openTab(page, "Palette");
  await expect(page.getByRole("region", { name: "palette-preview" })).toBeVisible();

  await openTab(page, "Validation");
  await page.getByRole("button", { name: "Validate job", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Errors (0)" })).toBeVisible();

  await openTab(page, "Lineage");
  await expect(page.getByText(`${jobId}-candidate`).first()).toBeVisible();
  await expect(page.getByText(`${jobId}-export`).first()).toBeVisible();

  await openTab(page, "Report");
  await expect(page.getByRole("heading", { name: `Report for ${jobId}` })).toBeVisible();
  const bundle = page.getByRole("list", { name: "bundle-entries" });
  await expect(bundle).toBeVisible();
  for (const entry of ["manifest.json", "report.json", "lineage.json", "hashes.json"]) {
    const pattern = new RegExp(`^${entry.replace(".", "\\.")} \\(\\d+ bytes\\)$`);
    await expect(bundle.getByText(pattern)).toBeVisible();
  }
  await expect(bundle.getByRole("button", { name: "Download report.json" })).toBeVisible();

  await openTab(page, "Timeline");
  const timeline = page.getByRole("list", { name: "job-timeline" });
  await expect(timeline).toBeVisible();
  await expect(timeline.getByRole("listitem").filter({ hasText: "transition" }).first()).toBeVisible();
});

test("rejects a candidate and retries it into a new job", async ({ page }) => {
  const rejectedId = await createJob(page, "a cautious mage, neutral expression");

  buildCandidate(rejectedId);
  await openJob(page, rejectedId, "waiting_for_review");

  await page
    .getByLabel("Rejection reason for candidate/package/hero.png", { exact: true })
    .fill("silhouette drifts from the reference");
  await page.getByRole("button", { name: "Reject candidate/package/hero.png" }).click();

  await expect(
    page.getByText(
      `Latest review: rejected by ${reviewer}. Reason: silhouette drifts from the reference`,
    ),
  ).toBeVisible();
  await expect(selectionStatus(page)).toHaveText(`Selected job ${rejectedId} is failed.`);

  await page.getByRole("button", { name: "Retry job", exact: true }).click();
  await expect(selectionStatus(page)).toHaveText(/is created\.$/);

  const retryId = await selectedJobId(page);
  expect(retryId).not.toEqual(rejectedId);
  await expect(page.getByRole("button", { name: `${rejectedId} — failed` })).toBeVisible();

  buildCandidate(retryId);
  await openJob(page, retryId, "waiting_for_review");

  await openTab(page, "Lineage");
  await expect(page.getByText(`${retryId}-candidate`).first()).toBeVisible();
  await expect(page.getByText(`${rejectedId}-candidate`).first()).toBeVisible();
});

test("edits a mask draft for the selected job", async ({ page }) => {
  const jobId = await createJob(page, "a stoic archer, neutral expression");

  buildCandidate(jobId);
  await openJob(page, jobId, "waiting_for_review");

  await openTab(page, "Mask");
  await expect(page.getByRole("region", { name: "mask-editor-panel" })).toBeVisible();
  await expect(page.getByText("Painted mask cells: 0")).toBeVisible();

  const surface = page.getByLabel("mask-paint-surface", { exact: true });
  await surface.focus();
  await surface.press("ArrowRight");
  await surface.press("ArrowDown");
  await surface.press("Space");
  await expect(page.getByText("Painted mask cells: 1")).toBeVisible();

  await page.getByRole("button", { name: "Clear mask", exact: true }).click();
  await expect(page.getByText("Painted mask cells: 0")).toBeVisible();
});
