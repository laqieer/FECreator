import "@testing-library/jest-dom/vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { useJobEvents } from "./useJobEvents";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }

  close() {
    this.onclose?.();
  }
}

function Probe({ jobId, baseUrl }: { jobId: string; baseUrl?: string }) {
  const snapshot = useJobEvents(jobId, baseUrl);
  return (
    <output>
      {snapshot.connectionState}:{snapshot.events.length}:{snapshot.error ?? "none"}
    </output>
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("opens the frozen websocket endpoint and returns the snapshot", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  render(<Probe jobId="job-7" baseUrl="http://127.0.0.1:8000" />);

  expect(MockWebSocket.instances[0]?.url).toBe("ws://127.0.0.1:8000/ws/jobs/job-7");
  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({
      data: JSON.stringify({
        events: [{ seq: 0, at: "2026-07-24T00:00:00+00:00", kind: "created", message: "job created" }],
      }),
    });
  });

  await waitFor(() => expect(screen.getByText("live:1:none")).toBeInTheDocument());
});
