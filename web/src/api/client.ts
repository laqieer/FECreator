import type { Diagnostic, Job, Manifest } from "./types";

export interface ApiClient {
  listAssets(): Promise<string[]>;
  listSpecs(): Promise<string[]>;
  listProviders(): Promise<string[]>;
  createJob(manifest: Manifest): Promise<Job>;
  getJob(id: string): Promise<Job>;
  validate(spec: string, path: string): Promise<Diagnostic[]>;
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

async function requestJson<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`${init?.method ?? "GET"} ${url} -> ${response.status}`);
  }
  return (await response.json()) as T;
}

export function httpClient(baseUrl = ""): ApiClient {
  const root = normalizeBaseUrl(baseUrl);

  return {
    listAssets: () => requestJson<string[]>(`${root}/api/assets`),
    listSpecs: () => requestJson<string[]>(`${root}/api/specs`),
    listProviders: () => requestJson<string[]>(`${root}/api/providers`),
    createJob: (manifest) =>
      requestJson<Job>(`${root}/api/jobs`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(manifest),
      }),
    getJob: (id) => requestJson<Job>(`${root}/api/jobs/${id}`),
    validate: (spec, path) =>
      requestJson<Diagnostic[]>(`${root}/api/validate`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ spec_id: spec, package_dir: path }),
      }),
  };
}
