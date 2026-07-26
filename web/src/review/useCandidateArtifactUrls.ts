import { useEffect, useState } from "react";
import type { ApiClient } from "../api/client";
import type { CandidateSnapshot } from "../api/types";

export interface CandidateArtifactUrl {
  role: string;
  path: string;
  url: string;
}

export type PaletteEntry = [number, number, number];

interface CandidateArtifactUrls {
  artifacts: CandidateArtifactUrl[];
  palette: PaletteEntry[];
  loading: boolean;
  error: string | null;
}

const initialState: CandidateArtifactUrls = {
  artifacts: [],
  palette: [],
  loading: false,
  error: null,
};

function toErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Unable to load review images.";
}

export function parseJascPalette(text: string): PaletteEntry[] {
  const lines = text.trim().split(/\r?\n/);
  if (lines.length < 3 || lines[0] !== "JASC-PAL" || lines[1] !== "0100") {
    throw new Error("Candidate palette is not valid JASC-PAL.");
  }
  const count = Number(lines[2]);
  if (!Number.isInteger(count) || count < 1 || count > 16 || lines.length !== count + 3) {
    throw new Error("Candidate palette has an invalid entry count.");
  }

  return lines.slice(3).map((line) => {
    const values = line.trim().split(/\s+/).map(Number);
    if (
      values.length !== 3 ||
      values.some((value) => !Number.isInteger(value) || value < 0 || value > 255)
    ) {
      throw new Error("Candidate palette has an invalid color entry.");
    }
    return [values[0]!, values[1]!, values[2]!] as PaletteEntry;
  });
}

export function useCandidateArtifactUrls(
  api: ApiClient,
  jobId: string | null,
  candidate: CandidateSnapshot | null,
): CandidateArtifactUrls {
  const [state, setState] = useState<CandidateArtifactUrls>(initialState);

  useEffect(() => {
    const imageArtifacts =
      candidate?.artifacts.filter((artifact) => artifact.media_type.startsWith("image/")) ?? [];
    const paletteArtifact = candidate?.artifacts.find((artifact) => artifact.role === "palette");
    if (jobId === null || (imageArtifacts.length === 0 && paletteArtifact === undefined)) {
      setState(initialState);
      return undefined;
    }

    let active = true;
    const urls: string[] = [];
    setState({ artifacts: [], palette: [], loading: true, error: null });

    void Promise.all([
      Promise.all(
        imageArtifacts.map(async (artifact) => {
          const blob = await api.getArtifact(jobId, artifact.path);
          const url = URL.createObjectURL(blob);
          if (!active) {
            URL.revokeObjectURL(url);
            return null;
          }
          urls.push(url);
          return { role: artifact.role, path: artifact.path, url };
        }),
      ),
      paletteArtifact
        ? api.getArtifact(jobId, paletteArtifact.path).then((blob) => blob.text()).then(parseJascPalette)
        : Promise.resolve([]),
    ])
      .then(([artifacts, palette]) => {
        if (active) {
          setState({
            artifacts: artifacts.filter((artifact): artifact is CandidateArtifactUrl => artifact !== null),
            palette,
            loading: false,
            error: null,
          });
        }
      })
      .catch((cause: unknown) => {
        if (active) {
          active = false;
          urls.forEach((url) => URL.revokeObjectURL(url));
          urls.length = 0;
          setState({ artifacts: [], palette: [], loading: false, error: toErrorMessage(cause) });
        }
      });

    return () => {
      active = false;
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [api, candidate, jobId]);

  return state;
}
