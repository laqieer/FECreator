export interface JobEventConnection {
  onopen: (() => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
  onerror: (() => void) | null;
  onclose: (() => void) | null;
  close(): void;
}

export interface JobEventSource {
  connect(jobId: string): JobEventConnection;
}
