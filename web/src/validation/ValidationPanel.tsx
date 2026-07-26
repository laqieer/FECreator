import { useQuery } from "@tanstack/react-query";
import type { Diagnostic, Severity } from "../api/types";
import { useApiClient } from "../api/context";

const groups: Array<{ severity: Severity; heading: string }> = [
  { severity: "error", heading: "Errors" },
  { severity: "warning", heading: "Warnings" },
  { severity: "info", heading: "Information" },
];

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
  const query = useQuery({
    queryKey: ["job-validation", jobId, refreshKey],
    enabled: jobId !== null,
    queryFn: () => api.validateJob(jobId!),
  });
  const diagnostics = query.data ?? [];

  return (
    <section aria-label="validation-panel">
      <h2>Validation</h2>
      {targetSpec ? <p>Target: {targetSpec}</p> : <p>Select a job to validate.</p>}
      {query.isPending ? <p role="status">Validating selected job…</p> : null}
      {query.isError ? <p role="alert">Unable to validate the selected job.</p> : null}
      {jobId ? (
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
