import { useQuery } from "@tanstack/react-query";
import type { Diagnostic, Severity } from "../api/types";
import { ApiError } from "../api/client";
import { useApiClient } from "../api/context";

const groups: Array<{ severity: Severity; heading: string }> = [
  { severity: "error", heading: "Errors" },
  { severity: "warning", heading: "Warnings" },
  { severity: "info", heading: "Information" },
];

function failureDiagnostics(cause: unknown): Diagnostic[] | null {
  return cause instanceof ApiError && cause.diagnostics !== null && cause.diagnostics.length > 0
    ? cause.diagnostics
    : null;
}

function failureMessage(cause: unknown): string {
  if (cause instanceof ApiError) {
    return `${cause.method} ${cause.url} failed with status ${cause.status}.`;
  }
  return cause instanceof Error ? cause.message : "Unable to validate the selected job.";
}

export function ValidationPanel({
  jobId,
  targetSpec,
  refreshKey = 0,
}: {
  jobId: string | null;
  targetSpec: string | null;
  refreshKey?: number;
}) {
  const api = useApiClient();
  const enabled = jobId !== null;
  const query = useQuery({
    queryKey: ["job-validation", jobId, refreshKey],
    enabled,
    retry: false,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    queryFn: () => api.validateJob(jobId!),
  });
  const diagnostics = query.data ?? [];
  const failure = query.isError ? query.error : null;
  const structured = failureDiagnostics(failure);

  return (
    <section aria-label="validation-panel">
      <h2>Validation</h2>
      {targetSpec ? <p>Target: {targetSpec}</p> : <p>Select a job to validate.</p>}
      {enabled && query.isLoading ? <p role="status">Validating selected job…</p> : null}
      {enabled && failure !== null ? (
        <div role="alert">
          <p>Unable to validate the selected job: {failureMessage(failure)}</p>
          {structured ? (
            <ul aria-label="validation-failure-diagnostics">
              {structured.map((diagnostic) => (
                <li key={`${diagnostic.code}-${diagnostic.message}`}>
                  <strong>{diagnostic.code}</strong>: {diagnostic.message}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
      {enabled ? (
        <button type="button" disabled={query.isFetching} onClick={() => void query.refetch()}>
          Validate job
        </button>
      ) : null}
      {groups.map(({ severity, heading }) => {
        const matching = diagnostics.filter((diagnostic) => diagnostic.severity === severity);
        return (
          <section key={severity} aria-label={`${heading.toLowerCase()} diagnostics`}>
            <h3>{heading} ({matching.length})</h3>
            {matching.length === 0 ? (
              <p>No {heading.toLowerCase()}.</p>
            ) : (
              <ul>
                {matching.map((diagnostic: Diagnostic) => (
                  <li key={`${diagnostic.code}-${diagnostic.message}`}>
                    <strong>{diagnostic.code}</strong>: {diagnostic.message}
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </section>
  );
}
