import { useEffect, useState } from "react";
import type { ApiClient } from "../api/client";
import type { CandidateSnapshot } from "../api/types";

export interface CandidateArtifactUrl {
  path: string;
  url: string;
}

interface CandidateArtifactUrls {
  artifacts: CandidateArtifactUrl[];
  loading: boolean;
  error: string | null;
}

const initialState: CandidateArtifactUrls = {
  artifacts: [],
  loading: false,
  error: null,
};

function toErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Unable to load review images.";
}

export function useCandidateArtifactUrls(
  api: ApiClient,
  jobId: string | null,
  candidate: CandidateSnapshot | null,
): CandidateArtifactUrls {
  const [state, setState] = useState<CandidateArtifactUrls>(initialState);

  useEffect(() => {
    const imageArtifacts = candidate?.artifacts.filter((artifact) =>
      artifact.media_type.startsWith("image/"),
    );
    if (jobId === null || imageArtifacts === undefined || imageArtifacts.length === 0) {
      setState(initialState);
      return undefined;
    }

    let active = true;
    const urls: string[] = [];
    setState({ artifacts: [], loading: true, error: null });

    void Promise.all(
      imageArtifacts.map(async (artifact) => {
        const blob = await api.getArtifact(jobId, artifact.path);
        const url = URL.createObjectURL(blob);
        if (!active) {
          URL.revokeObjectURL(url);
          return null;
        }
        urls.push(url);
        return { path: artifact.path, url };
      }),
    )
      .then((artifacts) => {
        if (active) {
          setState({
            artifacts: artifacts.filter((artifact): artifact is CandidateArtifactUrl => artifact !== null),
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
          setState({ artifacts: [], loading: false, error: toErrorMessage(cause) });
        }
      });

    return () => {
      active = false;
      urls.forEach((url) => URL.revokeObjectURL(url));
    };
  }, [api, candidate, jobId]);

  return state;
}
