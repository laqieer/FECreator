import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import type { ApiClient } from "../api/client";
import type { CandidateSnapshot } from "../api/types";
import { createStubApiClient } from "../test/util";
import { parseJascPalette, useCandidateArtifactUrls } from "./useCandidateArtifactUrls";

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve;
  });
  return { promise, resolve };
}

function candidate(jobId: string, path: string): CandidateSnapshot {
  return {
    version: "1.0",
    job_id: jobId,
    lineage_id: `${jobId}-candidate`,
    artifacts: [
      {
        role: "portrait",
        path,
        sha256: "0".repeat(64),
        media_type: "image/png",
      },
    ],
    diagnostics: [],
    metrics: {},
    created_at: "2026-07-24T00:00:00+00:00",
  };
}

function ArtifactUrls({
  api,
  jobId,
  snapshot,
}: {
  api: ApiClient;
  jobId: string | null;
  snapshot: CandidateSnapshot | null;
}) {
  const { artifacts, error, loading } = useCandidateArtifactUrls(api, jobId, snapshot);
  return (
    <>
      {loading ? <p role="status">Loading review images…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {artifacts.map((artifact) => (
        <img key={artifact.path} src={artifact.url} alt={artifact.path} />
      ))}
    </>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
});

test("loads artifacts through the API and revokes stale and removed object URLs", async () => {
  const first = deferred<Blob>();
  const second = deferred<Blob>();
  const getArtifact = vi.fn((jobId: string) => (jobId === "job-a" ? first.promise : second.promise));
  const createObjectURL = vi.fn((blob: Blob) => `blob:${blob.size}`);
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  const api = createStubApiClient({ getArtifact });
  const { rerender, unmount } = render(
    <ArtifactUrls api={api} jobId="job-a" snapshot={candidate("job-a", "a.png")} />,
  );

  expect(getArtifact).toHaveBeenCalledWith("job-a", "a.png");
  rerender(<ArtifactUrls api={api} jobId="job-b" snapshot={candidate("job-b", "b.png")} />);
  expect(getArtifact).toHaveBeenCalledWith("job-b", "b.png");

  first.resolve(new Blob(["old"]));
  second.resolve(new Blob(["newer"]));

  await waitFor(() => expect(screen.getByAltText("b.png")).toHaveAttribute("src", "blob:5"));
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:3");

  unmount();
  expect(revokeObjectURL).toHaveBeenCalledWith("blob:5");
});

test("parses the persisted candidate JASC palette sidecar", () => {
  expect(
    parseJascPalette(`JASC-PAL
0100
2
0 248 0
80 96 200
`),
  ).toEqual([
    [0, 248, 0],
    [80, 96, 200],
  ]);
});

test("loads a candidate palette sidecar through the artifact API", async () => {
  const createObjectURL = vi.fn(() => "blob:portrait");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { createObjectURL, revokeObjectURL });
  const snapshot: CandidateSnapshot = {
    ...candidate("job-a", "candidate/package/portrait.png"),
    artifacts: [
      {
        role: "portrait",
        path: "candidate/package/portrait.png",
        sha256: "0".repeat(64),
        media_type: "image/png",
      },
      {
        role: "palette",
        path: "candidate/package/portrait.pal",
        sha256: "1".repeat(64),
        media_type: "text/plain",
      },
    ],
  };
  const api = createStubApiClient({
    getArtifact: async (_jobId, path) =>
      path.endsWith(".pal")
        ? new Blob(["JASC-PAL\n0100\n1\n0 248 0\n"], { type: "text/plain" })
        : new Blob(["image"], { type: "image/png" }),
  });

  function PaletteEntries() {
    const { palette } = useCandidateArtifactUrls(api, "job-a", snapshot);
    return <p>{JSON.stringify(palette)}</p>;
  }

  render(<PaletteEntries />);

  expect(await screen.findByText("[[0,248,0]]")).toBeInTheDocument();
});
