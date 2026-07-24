import { afterEach, expect, test, vi } from "vitest";
import { webSocketJobEventSource } from "./webSocketEventSource";

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  url: string;
  constructor(url: string) {
    this.url = url;
    MockWebSocket.instances.push(this);
  }
  close() {}
}

afterEach(() => {
  vi.unstubAllGlobals();
  MockWebSocket.instances = [];
});

test("the real source connects to the encoded websocket endpoint", () => {
  vi.stubGlobal("WebSocket", MockWebSocket);
  webSocketJobEventSource("http://127.0.0.1:8000").connect("job 7/alpha");
  expect(MockWebSocket.instances[0]?.url).toBe("ws://127.0.0.1:8000/ws/jobs/job%207%2Falpha");
});
