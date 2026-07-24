import { useEffect, useState } from "react";
import type { JobEvent } from "../api/types";
import type { JobConnectionState } from "./JobTimeline";

export interface JobEventsSnapshot {
  events: JobEvent[];
  connectionState: JobConnectionState;
  error: string | null;
}

const initialSnapshot: JobEventsSnapshot = {
  events: [],
  connectionState: "idle",
  error: null,
};

function toWebSocketUrl(baseUrl: string, jobId: string): string {
  const origin = baseUrl || window.location.origin;
  const normalizedOrigin = origin.endsWith("/") ? origin.slice(0, -1) : origin;
  return normalizedOrigin.replace(/^http/, "ws") + `/ws/jobs/${jobId}`;
}

export function useJobEvents(jobId: string, baseUrl = ""): JobEventsSnapshot {
  const [snapshot, setSnapshot] = useState<JobEventsSnapshot>(initialSnapshot);

  useEffect(() => {
    if (!jobId) {
      setSnapshot(initialSnapshot);
      return undefined;
    }

    let active = true;
    const socket = new WebSocket(toWebSocketUrl(baseUrl, jobId));
    setSnapshot({ events: [], connectionState: "connecting", error: null });

    socket.onopen = () => {
      if (!active) {
        return;
      }
      setSnapshot((current) => ({ ...current, connectionState: "live", error: null }));
    };

    socket.onmessage = (message) => {
      if (!active) {
        return;
      }
      const payload = JSON.parse(message.data as string) as { events?: JobEvent[] };
      setSnapshot({
        events: payload.events ?? [],
        connectionState: "live",
        error: null,
      });
    };

    socket.onerror = () => {
      if (!active) {
        return;
      }
      setSnapshot((current) => ({
        ...current,
        connectionState: "error",
        error: "Timeline connection failed.",
      }));
    };

    socket.onclose = () => {
      if (!active) {
        return;
      }
      setSnapshot((current) =>
        current.connectionState === "error"
          ? current
          : {
              ...current,
              connectionState: "disconnected",
            },
      );
    };

    return () => {
      active = false;
      socket.close();
    };
  }, [baseUrl, jobId]);

  return snapshot;
}
