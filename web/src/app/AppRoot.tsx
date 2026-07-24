import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { ApiClientProvider } from "../api/context";
import { DemoBanner } from "../demo/DemoBanner";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import { App } from "./App";
import type { Composition } from "./composition";

export function AppRoot({ composition }: { composition: Composition }) {
  const [queryClient] = useState(() => new QueryClient());

  return (
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={composition.client}>
        <JobEventSourceProvider source={composition.eventSource}>
          {composition.demo ? <DemoBanner /> : null}
          <App />
        </JobEventSourceProvider>
      </ApiClientProvider>
    </QueryClientProvider>
  );
}
