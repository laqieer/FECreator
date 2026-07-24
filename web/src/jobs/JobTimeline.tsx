import type { JobEvent, JobState } from "../api/types";

export type JobConnectionState = "idle" | "connecting" | "live" | "complete" | "disconnected" | "error";

export interface JobTimelineProps {
  events: JobEvent[];
  connectionState?: JobConnectionState;
  terminalState?: Extract<JobState, "completed" | "failed" | "cancelled"> | null;
  errorMessage?: string | null;
}

function ConnectionBanner({ state, errorMessage }: { state: JobConnectionState; errorMessage?: string | null }) {
  if (state === "error") {
    return <p role="alert">{errorMessage ?? "Timeline connection failed."}</p>;
  }

  if (state === "disconnected") {
    return <p role="alert">Timeline disconnected before a snapshot was received.</p>;
  }

  if (state === "connecting") {
    return <p role="status">Connecting to timeline…</p>;
  }

  if (state === "live") {
    return <p role="status">Timeline live.</p>;
  }

  if (state === "complete") {
    return <p role="status">Timeline snapshot complete.</p>;
  }

  return <p role="status">Timeline idle.</p>;
}

function TerminalBanner({ state }: { state: JobTimelineProps["terminalState"] }) {
  if (state === null || state === undefined) {
    return null;
  }

  return <p role="status">Job ended in {state}.</p>;
}

export function JobTimeline({
  events,
  connectionState = "idle",
  terminalState = null,
  errorMessage = null,
}: JobTimelineProps) {
  return (
    <section aria-label="job-timeline-panel">
      <ConnectionBanner state={connectionState} errorMessage={errorMessage} />
      <TerminalBanner state={terminalState} />
      {events.length === 0 ? (
        <p>No job events yet.</p>
      ) : (
        <ol aria-label="job-timeline">
          {events.map((event) => (
            <li key={event.seq}>
              <strong>{event.kind}</strong>
              {" — "}
              <span>{event.message}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}