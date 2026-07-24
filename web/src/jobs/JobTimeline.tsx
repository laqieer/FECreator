import type { JobEvent, JobState } from "../api/types";

export type JobConnectionState = "idle" | "connecting" | "live" | "disconnected" | "error";

export interface JobTimelineProps {
  events: JobEvent[];
  connectionState?: JobConnectionState;
  terminalState?: Extract<JobState, "completed" | "failed" | "cancelled"> | null;
}

function ConnectionBanner({ state }: { state: JobConnectionState }) {
  if (state === "disconnected") {
    return <p role="alert">Timeline disconnected</p>;
  }

  if (state === "error") {
    return <p role="alert">Timeline connection failed.</p>;
  }

  if (state === "connecting") {
    return <p role="status">Connecting to timeline…</p>;
  }

  if (state === "live") {
    return <p role="status">Timeline live.</p>;
  }

  return <p role="status">Timeline idle.</p>;
}

function TerminalBanner({ state }: { state: JobTimelineProps["terminalState"] }) {
  if (state === null || state === undefined) {
    return null;
  }

  return <p role="status">Job ended in {state}.</p>;
}

export function JobTimeline({ events, connectionState = "idle", terminalState = null }: JobTimelineProps) {
  return (
    <section aria-label="job-timeline-panel">
      <ConnectionBanner state={connectionState} />
      <TerminalBanner state={terminalState} />
      {events.length === 0 ? (
        <p>No job events yet.</p>
      ) : (
        <ol aria-label="job-timeline">
          {events.map((event) => (
            <li key={event.seq}>
              <strong>{event.kind}</strong>
              <span> — {event.message}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
