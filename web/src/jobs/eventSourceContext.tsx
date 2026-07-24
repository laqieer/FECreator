import { createContext, useContext, type ReactNode } from "react";
import type { JobEventSource } from "./eventSource";

const JobEventSourceContext = createContext<JobEventSource | null>(null);

export function JobEventSourceProvider({ source, children }: { source: JobEventSource; children: ReactNode }) {
  return <JobEventSourceContext.Provider value={source}>{children}</JobEventSourceContext.Provider>;
}

export function useJobEventSource(): JobEventSource {
  const source = useContext(JobEventSourceContext);
  if (source === null) {
    throw new Error("JobEventSource not provided");
  }
  return source;
}