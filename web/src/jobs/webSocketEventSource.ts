import type { JobEventConnection, JobEventSource } from "./eventSource";
import { toWebSocketUrl } from "./useJobEvents";

export function webSocketJobEventSource(baseUrl = ""): JobEventSource {
  return {
    connect: (jobId) => new WebSocket(toWebSocketUrl(baseUrl, jobId)) as unknown as JobEventConnection,
  };
}