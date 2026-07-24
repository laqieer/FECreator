import { createContext, useContext, type ReactNode } from "react";
import type { ApiClient } from "./client";

const ApiClientContext = createContext<ApiClient | null>(null);

interface ApiClientProviderProps {
  client: ApiClient;
  children: ReactNode;
}

export function ApiClientProvider({ client, children }: ApiClientProviderProps) {
  return <ApiClientContext.Provider value={client}>{children}</ApiClientContext.Provider>;
}

export function useApiClient(): ApiClient {
  const client = useContext(ApiClientContext);
  if (client === null) {
    throw new Error("ApiClient not provided");
  }
  return client;
}
