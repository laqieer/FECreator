import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { httpClient } from "./api/client";
import { ApiClientProvider } from "./api/context";

const queryClient = new QueryClient();
const rootElement = document.getElementById("root");

if (rootElement) {
  createRoot(rootElement).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ApiClientProvider client={httpClient()}>
          <App />
        </ApiClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}
