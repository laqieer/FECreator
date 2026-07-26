import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { useApiClient } from "../api/context";

const REVOKE_DELAY_MS = 60_000;

function filename(path: string): string {
  return path.split("/").filter(Boolean).at(-1) ?? "bundle-file";
}

function errorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "Unable to download the bundle file.";
}

export function ReportBundlePanel({ jobId, refreshKey = 0 }: { jobId: string | null; refreshKey?: number }) {
  const api = useApiClient();
  const [downloadError, setDownloadError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState<string | null>(null);
  const pendingRevocations = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const enabled = jobId !== null;
  const report = useQuery({
    queryKey: ["job-report", jobId, refreshKey],
    enabled,
    queryFn: () => api.getJobReport(jobId!),
  });
  const bundle = useQuery({
    queryKey: ["job-bundle", jobId, refreshKey],
    enabled,
    queryFn: () => api.listBundleEntries(jobId!),
  });

  useEffect(() => {
    const revocations = pendingRevocations.current;
    return () => {
      for (const [objectUrl, timer] of revocations) {
        clearTimeout(timer);
        URL.revokeObjectURL(objectUrl);
      }
      revocations.clear();
    };
  }, []);

  const startDownload = (objectUrl: string, name: string) => {
    const anchor = document.createElement("a");
    anchor.href = objectUrl;
    anchor.download = name;
    anchor.rel = "noopener";
    anchor.style.display = "none";
    document.body.appendChild(anchor);
    try {
      anchor.click();
    } finally {
      anchor.remove();
    }
    const timer = setTimeout(() => {
      pendingRevocations.current.delete(objectUrl);
      URL.revokeObjectURL(objectUrl);
    }, REVOKE_DELAY_MS);
    pendingRevocations.current.set(objectUrl, timer);
  };

  const download = async (path: string) => {
    if (jobId === null) {
      return;
    }
    setDownloading(path);
    setDownloadError(null);
    let objectUrl: string | null = null;
    try {
      const blob = await api.getBundleFile(jobId, path);
      objectUrl = URL.createObjectURL(blob);
      startDownload(objectUrl, filename(path));
    } catch (cause) {
      if (objectUrl !== null) {
        URL.revokeObjectURL(objectUrl);
      }
      setDownloadError(errorMessage(cause));
    } finally {
      setDownloading(null);
    }
  };

  return (
    <section aria-label="report-bundle-panel">
      <h2>Report and bundle</h2>
      {enabled && report.isLoading ? <p role="status">Loading sanitized report…</p> : null}
      {enabled && report.isError ? <p role="alert">Unable to load the sanitized report.</p> : null}
      {report.data ? (
        <section aria-label="sanitized-report">
          <h3>Report for {jobId}</h3>
          <p>
            State: {report.data.state}; revision: {report.data.revision}.
          </p>
          <p>Diagnostics: {report.data.diagnostics.length}; output hashes: {report.data.output_hashes.length}.</p>
        </section>
      ) : null}
      {enabled && bundle.isLoading ? <p role="status">Loading bundle entries…</p> : null}
      {enabled && bundle.isError ? <p role="alert">Unable to load bundle entries.</p> : null}
      {downloadError ? <p role="alert">{downloadError}</p> : null}
      {bundle.data ? (
        <ul aria-label="bundle-entries">
          {bundle.data.map((entry) => (
            <li key={entry.path}>
              <span>{entry.path} ({entry.size_bytes} bytes)</span>
              <button
                type="button"
                disabled={downloading !== null}
                onClick={() => void download(entry.path)}
              >
                Download {filename(entry.path)}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
      {jobId === null ? <p>Select a job to load its report and bundle.</p> : null}
    </section>
  );
}
