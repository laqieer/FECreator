import { expect, test, type Locator, type Page, type Request } from "@playwright/test";

test.describe.configure({ mode: "serial" });

const seedJobId = "demo-portrait-neutral";
const allowedPrefixes = ["blob:", "data:"];

interface NetworkLog {
  readonly all: string[];
  readonly offending: string[];
}

/**
 * Demo mode must stay completely offline: no `/api` call, no WebSocket, no
 * upload, and no request outside the static bundle it was served from.
 */
function watchNetwork(page: Page, baseUrl: string): NetworkLog {
  const all: string[] = [];
  const offending: string[] = [];
  const origin = new URL(baseUrl).origin;

  const record = (request: Request) => {
    const url = request.url();
    const type = request.resourceType();
    all.push(`${type} ${request.method()} ${url}`);
    const allowed =
      allowedPrefixes.some((prefix) => url.startsWith(prefix)) || url.startsWith(`${origin}/`);
    if (url.includes("/api/") || type === "fetch" || type === "xhr" || !allowed) {
      offending.push(`${type} ${request.method()} ${url}`);
    }
    if (request.method() !== "GET") {
      offending.push(`${request.method()} ${url}`);
    }
  };

  page.on("request", record);
  page.on("websocket", (socket) => offending.push(`websocket ${socket.url()}`));
  return { all, offending };
}

function selectionStatus(page: Page): Locator {
  return page.locator('p[role="status"]', { hasText: /^Selected job / });
}

function openTab(page: Page, name: string): Promise<void> {
  return page.getByRole("tab", { name, exact: true }).click();
}

test("demo review flow stays offline", async ({ page, baseURL }) => {
  const network = watchNetwork(page, baseURL!);

  await page.goto("./");
  await expect(page.getByRole("note", { name: "Demo mode notice" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "FECreator", level: 1 })).toBeVisible();

  const queued = page.getByRole("button", { name: `${seedJobId} — completed` });
  await expect(queued).toBeVisible();
  await queued.click();
  await expect(selectionStatus(page)).toHaveText(`Selected job ${seedJobId} is completed.`);

  await expect(
    page.getByRole("img", { name: "Candidate candidate/package/portrait.png" }),
  ).toBeVisible();
  await expect(page.getByText("Latest review: approved by reviewer.")).toBeVisible();

  await openTab(page, "Palette");
  await expect(page.getByRole("region", { name: "palette-preview" })).toBeVisible();

  await openTab(page, "Mask");
  await expect(page.getByRole("region", { name: "mask-editor-panel" })).toBeVisible();
  const surface = page.getByLabel("mask-paint-surface", { exact: true });
  await surface.focus();
  await surface.press("ArrowRight");
  await surface.press("Space");
  await expect(page.getByText("Painted mask cells: 1")).toBeVisible();

  await openTab(page, "Validation");
  await page.getByRole("button", { name: "Validate job", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Errors (0)" })).toBeVisible();
  await expect(page.getByText("portrait.palette.count")).toBeVisible();

  await openTab(page, "Lineage");
  await expect(page.getByText(`${seedJobId}-candidate`).first()).toBeVisible();

  await openTab(page, "Report");
  await expect(page.getByRole("heading", { name: `Report for ${seedJobId}` })).toBeVisible();
  await expect(page.getByRole("list", { name: "bundle-entries" }).getByRole("listitem")).toHaveCount(
    4,
  );

  await openTab(page, "Timeline");
  await expect(page.getByRole("list", { name: "job-timeline" }).getByRole("listitem")).toHaveCount(4);

  expect(network.offending).toEqual([]);
  expect(network.all.length).toBeGreaterThan(0);
});

test("demo mode creates, reviews, and finalizes an in-memory job", async ({ page, baseURL }) => {
  const network = watchNetwork(page, baseURL!);

  await page.goto("./");
  await page.getByLabel(/^Provider/).selectOption("fake");
  await page.getByLabel(/^Text source/).fill("a demo hero");
  await page.getByRole("button", { name: "Create job", exact: true }).click();

  await expect(selectionStatus(page)).toHaveText("Selected job demo-job-1 is created.");

  await page.getByRole("button", { name: "Plan sources", exact: true }).click();
  await expect(page.getByRole("list", { name: "source-prompts" })).toBeVisible();

  await page.getByLabel("Source files", { exact: true }).setInputFiles({
    name: "neutral.png",
    mimeType: "image/png",
    buffer: Buffer.from("demo-source"),
  });
  await page.getByRole("button", { name: "Submit sources", exact: true }).click();
  await expect(selectionStatus(page)).toHaveText("Selected job demo-job-1 is waiting_for_review.");

  await page.getByRole("button", { name: "Approve candidate/package/portrait.png" }).click();
  await expect(page.getByText("Latest review: approved by local-user.")).toBeVisible();

  await page.getByRole("button", { name: "Finalize review", exact: true }).click();
  await expect(selectionStatus(page)).toHaveText("Selected job demo-job-1 is completed.");

  await openTab(page, "Report");
  await expect(page.getByRole("heading", { name: "Report for demo-job-1" })).toBeVisible();

  expect(network.offending).toEqual([]);
});

test("demo mode reloads back to the seeded fixtures", async ({ page, baseURL }) => {
  const network = watchNetwork(page, baseURL!);

  await page.goto("./");
  await expect(page.getByRole("button", { name: `${seedJobId} — completed` })).toBeVisible();
  await expect(page.getByRole("button", { name: /^demo-job-/ })).toHaveCount(0);

  expect(network.offending).toEqual([]);
});
