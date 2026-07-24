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

test("demo composition uses in-memory registries and never opens a socket", async () => {
  const webSocketSpy = vi.fn();
  vi.stubGlobal("WebSocket", webSocketSpy);
  const { client, eventSource, demo } = createComposition("demo");

  expect(demo).toBe(true);
  expect(await client.listAssets()).toEqual(["portrait"]);

  const connection = eventSource.connect("demo-job-1");
  connection.close();
  expect(webSocketSpy).not.toHaveBeenCalled();
});

test("local composition uses the HTTP client and the websocket event source", async () => {
  const fetchSpy = vi.fn().mockResolvedValue({ ok: true, json: async () => ["portrait"] });
  vi.stubGlobal("fetch", fetchSpy);
  vi.stubGlobal("WebSocket", MockWebSocket);
  const { client, eventSource, demo } = createComposition("local");

  expect(demo).toBe(false);
  await client.listAssets();
  expect(fetchSpy).toHaveBeenCalledWith("/api/assets", undefined);

  eventSource.connect("job-1");
  expect(MockWebSocket.instances[0]?.url).toBe("ws://localhost:3000/ws/jobs/job-1");
});