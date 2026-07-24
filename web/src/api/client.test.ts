import { afterEach, expect, test, vi } from "vitest";
import { httpClient } from "./client";
import type { Manifest } from "./types";

const manifest: Manifest = {
  version: "1.0",
  asset_type: "portrait",
  target_spec: "fe-gba-portrait-standard",
  workflow: "text_to_portrait",
  provider: "fake",
  sources: [{ kind: "text", ref: "heroic knight" }],
  params: {},
};

afterEach(() => {
  vi.unstubAllGlobals();
});

test("createJob posts the frozen backend manifest contract", async () => {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: true,
    json: async () => ({
      id: "job-1",
      state: "created",
      manifest,
      revision: 1,
      created_at: "2026-07-24T00:00:00+00:00",
      updated_at: "2026-07-24T00:00:00+00:00",
    }),
  });
  vi.stubGlobal("fetch", fetchMock);

  const job = await httpClient("http://127.0.0.1:8000/").createJob(manifest);

  expect(job.id).toBe("job-1");
  expect(fetchMock).toHaveBeenCalledWith(
    "http://127.0.0.1:8000/api/jobs",
    expect.objectContaining({
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(manifest),
    }),
  );
});

test("validate fails closed on non-ok responses", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => [] }),
  );

  await expect(httpClient("http://127.0.0.1:8000").validate("fe-gba-portrait-standard", "C:/work")).rejects.toThrow(
    "POST http://127.0.0.1:8000/api/validate -> 500",
  );
});
