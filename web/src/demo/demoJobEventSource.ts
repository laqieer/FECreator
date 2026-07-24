import type { JobEvent } from "../api/types";
import type { JobEventConnection, JobEventSource } from "../jobs/eventSource";
import { demoTimeline } from "./fixtures";

const STEP_MS = 5;

export function demoJobEventSource(timeline: readonly JobEvent[] = demoTimeline): JobEventSource {
  return {
    connect(jobId) {
      const timers: ReturnType<typeof setTimeout>[] = [];
      const connection: JobEventConnection = {
        onopen: null,
        onmessage: null,
        onerror: null,
        onclose: null,
        close() {
          for (const timer of timers) {
            clearTimeout(timer);
          }
          timers.length = 0;
        },
      };

      timers.push(setTimeout(() => connection.onopen?.(), 0));
      timers.push(
        setTimeout(() => {
          connection.onmessage?.({
            data: JSON.stringify({ job_id: jobId, events: timeline }),
          });
        }, STEP_MS),
      );
      timers.push(setTimeout(() => connection.onclose?.(), STEP_MS * 2));

      return connection;
    },
  };
}