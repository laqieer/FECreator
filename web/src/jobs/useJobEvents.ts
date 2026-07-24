import type { JobEvent, JobEventsPayload } from "../api/types";
import { useEffect, useState } from "react";
import type { JobConnectionState } from "./JobTimeline";
import { useJobEventSource } from "./eventSourceContext";

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

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isJsonScalar(value: unknown): value is string | number | boolean {
  return typeof value === "string" || typeof value === "number" || typeof value === "boolean";
}

function isJsonObject(value: unknown): value is Record<string, string | number | boolean> {
  return isRecord(value) && Object.values(value).every(isJsonScalar);
}

function isJobEvent(value: unknown): value is JobEvent {
  if (!isRecord(value)) {
    return false;
  }

  const { seq, at, kind, message, data } = value;
  const hasValidData = data === undefined || isJsonObject(data);

  return (
    typeof seq === "number" &&
    Number.isInteger(seq) &&
    seq >= 0 &&
    typeof at === "string" &&
    at.length > 0 &&
    typeof kind === "string" &&
    kind.length > 0 &&
    typeof message === "string" &&
    message.length > 0 &&
    hasValidData
  );
}

export function toWebSocketUrl(baseUrl: string, jobId: string): string {
  const origin = baseUrl || window.location.origin;
  const normalizedOrigin = origin.endsWith("/") ? origin.slice(0, -1) : origin;
  return normalizedOrigin.replace(/^http/, "ws") + `/ws/jobs/${encodeURIComponent(jobId)}`;
}

export function parseJobEventsPayload(rawData: unknown, expectedJobId: string): JobEventsPayload {
  if (typeof rawData !== "string") {
    throw new Error("Job events payload must be a JSON string.");
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(rawData);
  } catch {
    throw new Error("Malformed job events JSON.");
  }

  if (!isRecord(parsed)) {
    throw new Error("Job events payload must be an object.");
  }

  if (parsed.job_id !== expectedJobId) {
    throw new Error("Job events payload job id does not match the selected job.");
  }

  if (!Array.isArray(parsed.events)) {
    throw new Error("Job events payload must include an events array.");
  }

  if (!parsed.events.every(isJobEvent)) {
    throw new Error("Job events payload contains an invalid event.");
  }

  return {
    job_id: parsed.job_id,
    events: parsed.events,
  };
}

export function useJobEvents(jobId: string): JobEventsSnapshot {
  const source = useJobEventSource();
  const [snapshot, setSnapshot] = useState<JobEventsSnapshot>(initialSnapshot);

  useEffect(() => {
    if (!jobId) {
      setSnapshot(initialSnapshot);
      return undefined;
    }

    let active = true;
    let receivedSnapshot = false;
    let hasError = false;
    const socket = source.connect(jobId);
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

      try {
        const payload = parseJobEventsPayload(message.data, jobId);
        receivedSnapshot = true;
        hasError = false;
        setSnapshot({
          events: payload.events,
          connectionState: "live",
          error: null,
        });
      } catch (error) {
        hasError = true;
        setSnapshot({
          events: [],
          connectionState: "error",
          error: error instanceof Error ? error.message : "Job events payload failed validation.",
        });
        socket.close();
      }
    };

    socket.onerror = () => {
      if (!active) {
        return;
      }

      hasError = true;
      setSnapshot({
        events: [],
        connectionState: "error",
        error: "Timeline connection failed.",
      });
    };

    socket.onclose = () => {
      if (!active || hasError) {
        return;
      }

      setSnapshot((current) => ({
        ...current,
        connectionState: receivedSnapshot ? "complete" : "disconnected",
      }));
    };

    return () => {
      active = false;
      socket.close();
    };
  }, [jobId, source]);

  return snapshot;
}
