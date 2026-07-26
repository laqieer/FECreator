import type {
  ApprovalRecord,
  BundleEntry,
  CandidateSnapshot,
  Diagnostic,
  Job,
  JobResult,
  LineageNode,
  Manifest,
  ReferencePack,
  Report,
  SourcePlan,
} from "./types";

export interface ApiClient {
  listAssets(): Promise<string[]>;
  listSpecs(): Promise<string[]>;
  listProviders(): Promise<string[]>;
  listJobs(): Promise<Job[]>;
  createJob(manifest: Manifest): Promise<Job>;
  getJob(id: string): Promise<Job>;
  getJobCandidate(jobId: string): Promise<CandidateSnapshot>;
  listApprovals(jobId: string): Promise<ApprovalRecord[]>;
  planSources(jobId: string): Promise<SourcePlan>;
  submitSources(jobId: string, files: File[]): Promise<Job>;
  validate(spec: string, path: string): Promise<Diagnostic[]>;
  validateJob(jobId: string): Promise<Diagnostic[]>;
  getArtifact(jobId: string, path: string): Promise<Blob>;
  getJobReport(jobId: string): Promise<Report>;
  listBundleEntries(jobId: string): Promise<BundleEntry[]>;
  getBundleFile(jobId: string, path: string): Promise<Blob>;
  approveReview(jobId: string, actor: string): Promise<ApprovalRecord>;
  rejectReview(jobId: string, actor: string, reason: string): Promise<ApprovalRecord>;
  finalizeJob(jobId: string): Promise<JobResult>;
  retryJob(jobId: string, actor: string): Promise<Job>;
  cancelJob(jobId: string): Promise<Job>;
  listReferencePacks(): Promise<string[]>;
  listReferenceHistory(packId: string): Promise<ReferencePack[]>;
  getLineage(assetId: string): Promise<LineageNode>;
  getLineageAncestors(assetId: string): Promise<LineageNode[]>;
  getLineageChildren(assetId: string): Promise<LineageNode[]>;
}

export interface HttpApiClientOptions {
  baseUrl?: string;
  fetch?: typeof fetch;
}

function normalizeBaseUrl(baseUrl: string): string {
  return baseUrl.endsWith("/") ? baseUrl.slice(0, -1) : baseUrl;
}

function encodePathSegment(value: string): string {
  return encodeURIComponent(value);
}

function encodeRelativePath(value: string): string {
  return value.split("/").map(encodeURIComponent).join("/");
}

function isDiagnosticRecord(value: unknown): value is Diagnostic {
  if (typeof value !== "object" || value === null) {
    return false;
  }

  const candidate = value as Partial<Diagnostic>;
  return (
    typeof candidate.code === "string" &&
    typeof candidate.message === "string" &&
    (candidate.severity === "error" ||
      candidate.severity === "warning" ||
      candidate.severity === "info")
  );
}

async function parseErrorBody(response: Response): Promise<unknown> {
  const contentType = response.headers.get("content-type") ?? "";
  if (contentType.includes("application/json")) {
    try {
      return (await response.json()) as unknown;
    } catch {
      return null;
    }
  }

  try {
    return await response.text();
  } catch {
    return null;
  }
}

export class ApiError extends Error {
  readonly status: number;
  readonly method: string;
  readonly url: string;
  readonly diagnostics: Diagnostic[] | null;
  readonly body: unknown;

  constructor(
    method: string,
    url: string,
    status: number,
    body: unknown,
    diagnostics: Diagnostic[] | null,
  ) {
    super(`${method} ${url} -> ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.method = method;
    this.url = url;
    this.body = body;
    this.diagnostics = diagnostics;
  }
}

export class NotFoundError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "NotFoundError";
  }
}

export function isNotFoundError(cause: unknown): boolean {
  return (
    cause instanceof NotFoundError || (cause instanceof ApiError && cause.status === 404)
  );
}

async function ensureOk(response: Response, method: string, url: string): Promise<Response> {
  if (response.ok) {
    return response;
  }

  const body = await parseErrorBody(response);
  const diagnostics =
    Array.isArray(body) && body.every((item) => isDiagnosticRecord(item)) ? body : null;
  throw new ApiError(method, url, response.status, body, diagnostics);
}

async function requestJson<T>(
  fetchImpl: typeof fetch,
  url: string,
  init?: RequestInit,
): Promise<T> {
  const method = init?.method ?? "GET";
  const response = await fetchImpl(url, init);
  await ensureOk(response, method, url);
  return (await response.json()) as T;
}

async function requestBlob(
  fetchImpl: typeof fetch,
  url: string,
  init?: RequestInit,
): Promise<Blob> {
  const method = init?.method ?? "GET";
  const response = await fetchImpl(url, init);
  await ensureOk(response, method, url);
  return response.blob();
}

function jsonRequest(body: unknown): RequestInit {
  return {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  };
}

function fileUploadRequest(files: File[]): RequestInit {
  const body = new FormData();
  for (const file of files) {
    body.append("files", file);
  }
  return { method: "POST", body };
}

export function createHttpApiClient(options: HttpApiClientOptions = {}): ApiClient {
  const root = normalizeBaseUrl(options.baseUrl ?? "");
  const fetchImpl = options.fetch ?? fetch;

  const route = (path: string): string => `${root}${path}`;
  const jobRoute = (jobId: string, suffix = ""): string =>
    route(`/api/jobs/${encodePathSegment(jobId)}${suffix}`);
  const lineageRoute = (assetId: string, suffix = ""): string =>
    route(`/api/lineage/${encodePathSegment(assetId)}${suffix}`);
  const referenceRoute = (packId: string, suffix = ""): string =>
    route(`/api/references/${encodePathSegment(packId)}${suffix}`);

  return {
    listAssets: () => requestJson<string[]>(fetchImpl, route("/api/assets")),
    listSpecs: () => requestJson<string[]>(fetchImpl, route("/api/specs")),
    listProviders: () => requestJson<string[]>(fetchImpl, route("/api/providers")),
    listJobs: () => requestJson<Job[]>(fetchImpl, route("/api/jobs")),
    createJob: (manifest) => requestJson<Job>(fetchImpl, route("/api/jobs"), jsonRequest(manifest)),
    getJob: (id) => requestJson<Job>(fetchImpl, jobRoute(id)),
    getJobCandidate: (jobId) =>
      requestJson<CandidateSnapshot>(fetchImpl, jobRoute(jobId, "/candidate")),
    listApprovals: (jobId) =>
      requestJson<ApprovalRecord[]>(fetchImpl, jobRoute(jobId, "/approvals")),
    planSources: (jobId) =>
      requestJson<SourcePlan>(fetchImpl, jobRoute(jobId, "/plan-sources"), { method: "POST" }),
    submitSources: (jobId, files) =>
      requestJson<Job>(fetchImpl, jobRoute(jobId, "/sources"), fileUploadRequest(files)),
    validate: (spec, path) =>
      requestJson<Diagnostic[]>(
        fetchImpl,
        route("/api/validate"),
        jsonRequest({ spec_id: spec, package_dir: path }),
      ),
    validateJob: (jobId) =>
      requestJson<Diagnostic[]>(fetchImpl, jobRoute(jobId, "/validate"), { method: "POST" }),
    getArtifact: (jobId, path) =>
      requestBlob(fetchImpl, jobRoute(jobId, `/artifacts/${encodeRelativePath(path)}`)),
    getJobReport: (jobId) => requestJson<Report>(fetchImpl, jobRoute(jobId, "/report")),
    listBundleEntries: (jobId) =>
      requestJson<BundleEntry[]>(fetchImpl, jobRoute(jobId, "/bundle")),
    getBundleFile: (jobId, path) =>
      requestBlob(fetchImpl, jobRoute(jobId, `/bundle/${encodeRelativePath(path)}`)),
    approveReview: (jobId, actor) =>
      requestJson<ApprovalRecord>(fetchImpl, jobRoute(jobId, "/approve"), jsonRequest({ actor })),
    rejectReview: (jobId, actor, reason) =>
      requestJson<ApprovalRecord>(
        fetchImpl,
        jobRoute(jobId, "/reject"),
        jsonRequest({ actor, reason }),
      ),
    finalizeJob: (jobId) =>
      requestJson<JobResult>(fetchImpl, jobRoute(jobId, "/finalize"), { method: "POST" }),
    retryJob: (jobId, actor) =>
      requestJson<Job>(fetchImpl, jobRoute(jobId, "/retry"), jsonRequest({ actor })),
    cancelJob: (jobId) =>
      requestJson<Job>(fetchImpl, jobRoute(jobId, "/cancel"), { method: "POST" }),
    listReferencePacks: () => requestJson<string[]>(fetchImpl, route("/api/references")),
    listReferenceHistory: (packId) =>
      requestJson<ReferencePack[]>(fetchImpl, referenceRoute(packId, "/history")),
    getLineage: (assetId) => requestJson<LineageNode>(fetchImpl, lineageRoute(assetId)),
    getLineageAncestors: (assetId) =>
      requestJson<LineageNode[]>(fetchImpl, lineageRoute(assetId, "/ancestors")),
    getLineageChildren: (assetId) =>
      requestJson<LineageNode[]>(fetchImpl, lineageRoute(assetId, "/children")),
  };
}

export function httpClient(baseUrl = ""): ApiClient {
  return createHttpApiClient({ baseUrl });
}
