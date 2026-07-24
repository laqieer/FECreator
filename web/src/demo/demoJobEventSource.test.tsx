import "@testing-library/jest-dom/vitest";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { demoJobEventSource } from "./demoJobEventSource";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import { useJobEvents } from "../jobs/useJobEvents";

function Probe({ jobId }: { jobId: string }) {
  const snapshot = useJobEvents(jobId);
  return (
    <output>
      {snapshot.connectionState}:{snapshot.events.length}:{snapshot.error ?? "none"}
    </output>
  );
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("the demo source never constructs a WebSocket and completes a sample timeline", () => {
  const webSocketSpy = vi.fn();
  vi.stubGlobal("WebSocket", webSocketSpy);

  render(
    <JobEventSourceProvider source={demoJobEventSource()}>
      <Probe jobId="demo-job-1" />
    </JobEventSourceProvider>,
  );

  act(() => {
    vi.runAllTimers();
  });

  expect(webSocketSpy).not.toHaveBeenCalled();
  expect(screen.getByText("complete:4:none")).toBeInTheDocument();
});

test("closing clears pending timers before any callback fires", () => {
  const source = demoJobEventSource();
  const connection = source.connect("demo-job-1");
  const opened = vi.fn();
  connection.onopen = opened;

  connection.close();
  act(() => {
    vi.runAllTimers();
  });

  expect(opened).not.toHaveBeenCalled();
});