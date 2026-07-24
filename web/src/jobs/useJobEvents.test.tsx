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

test("opens the frozen websocket endpoint, encodes ids, and completes after one snapshot", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  render(<Probe jobId="job 7/alpha" baseUrl="http://127.0.0.1:8000" />);

  expect(MockWebSocket.instances[0]?.url).toBe("ws://127.0.0.1:8000/ws/jobs/job%207%2Falpha");
  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({
      data: JSON.stringify({
        job_id: "job 7/alpha",
        events: [{ seq: 0, at: "2026-07-24T00:00:00+00:00", kind: "created", message: "job created" }],
      }),
    });
    MockWebSocket.instances[0]?.onclose?.();
  });

  await waitFor(() => expect(screen.getByText("complete:1:none")).toBeInTheDocument());
});

test("fails closed on malformed websocket json", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  render(<Probe jobId="job-7" baseUrl="http://127.0.0.1:8000" />);

  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({ data: "{" });
  });

  await waitFor(() => expect(screen.getByText(/error:0:Malformed job events JSON\./)).toBeInTheDocument());
});

test("fails closed on websocket payloads without a valid events array", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  render(<Probe jobId="job-7" baseUrl="http://127.0.0.1:8000" />);

  act(() => {
    MockWebSocket.instances[0]?.onopen?.();
    MockWebSocket.instances[0]?.onmessage?.({ data: JSON.stringify({ job_id: "job-7", events: [{}] }) });
  });

  await waitFor(() =>
    expect(screen.getByText(/error:0:Job events payload contains an invalid event\./)).toBeInTheDocument(),
  );
});

test("surfaces an unexpected disconnect before any snapshot", async () => {
  vi.stubGlobal("WebSocket", MockWebSocket);

  render(<Probe jobId="job-7" baseUrl="http://127.0.0.1:8000" />);

  act(() => {
    MockWebSocket.instances[0]?.onclose?.();
  });

  await waitFor(() => expect(screen.getByText("disconnected:0:none")).toBeInTheDocument());
});
