import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { ApiClientProvider } from "../api/context";
import type { ApiClient } from "../api/client";
import { JobEventSourceProvider } from "../jobs/eventSourceContext";
import type { JobEventSource } from "../jobs/eventSource";
import { webSocketJobEventSource } from "../jobs/webSocketEventSource";

export function renderWithProviders(
  ui: ReactElement,
  client: ApiClient,
  source: JobEventSource = webSocketJobEventSource(),
) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ApiClientProvider client={client}>
        <JobEventSourceProvider source={source}>{ui}</JobEventSourceProvider>
      </ApiClientProvider>
    </QueryClientProvider>,
  );
}