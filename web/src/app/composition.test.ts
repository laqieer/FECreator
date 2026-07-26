import { afterEach, expect, test, vi } from "vitest";
import { createComposition } from "./composition";

class MockWebSocket {
  static instances: MockWebSocket[] = [];

  constructor(public url: string) {
    MockWebSocket.instances.push(this);
  }

  close() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("demo composition uses in-memory adapters for jobs, reports, and events without sockets", async () => {
  const webSocketSpy = vi.fn();
  vi.stubGlobal("WebSocket", webSocketSpy);
  const { client, eventSource, demo } = createComposition("demo");

  expect(demo).toBe(true);
  expect(await client.listJobs()).toEqual(
    expect.arrayContaining([expect.objectContaining({ id: "demo-portrait-neutral" })]),
  );
  expect(await client.getJobReport("demo-portrait-neutral")).toEqual(
    expect.objectContaining({ job_id: "demo-portrait-neutral" }),
  );

  const connection = eventSource.connect("demo-job-1");
  connection.close();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("local composition uses the HTTP client for expanded read endpoints and the websocket event source", async () => {
  const fetchSpy = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(["hero-pack"]), {
      status: 200,
      headers: { "content-type": "application/json" },
    }),
  );
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", MockWebSocket);
  const { client, eventSource, demo } = createComposition("local");

  expect(demo).toBe(false);
  await client.listReferencePacks();
  expect(fetchSpy).toHaveBeenCalledWith("/api/references", undefined);

  eventSource.connect("job-1");
  expect(MockWebSocket.instances[0]?.url).toBe("ws://localhost:3000/ws/jobs/job-1");
});
