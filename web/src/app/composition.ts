import type { ApiClient } from "../api/client";
import { httpClient } from "../api/client";
import type { AppMode } from "../config/constants";
import { DEMO_MODE } from "../config/constants";
import { demoClient } from "../demo/demoClient";
import { demoJobEventSource } from "../demo/demoJobEventSource";
import type { JobEventSource } from "../jobs/eventSource";
import { webSocketJobEventSource } from "../jobs/webSocketEventSource";

export interface Composition {
  client: ApiClient;
  eventSource: JobEventSource;
  demo: boolean;
}

export function createComposition(mode: AppMode): Composition {
  if (mode === DEMO_MODE) {
    return { client: demoClient(), eventSource: demoJobEventSource(), demo: true };
  }
  return { client: httpClient(), eventSource: webSocketJobEventSource(), demo: false };
}
