import type { Job } from "../api/types";

export interface JobQueueProps {
  jobs: Job[];
  selectedJobId: string | null;
  loading: boolean;
  error: string | null;
  onSelect: (jobId: string) => void;
}

export function JobQueue({ jobs, selectedJobId, loading, error, onSelect }: JobQueueProps) {
  return (
    <section aria-label="job-queue">
      <h2>Jobs</h2>
      {loading ? <p role="status">Loading jobs…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {!loading && !error && jobs.length === 0 ? <p>No persisted jobs yet.</p> : null}
      {jobs.length > 0 ? (
        <ul aria-label="persisted jobs">
          {jobs.map((job) => (
            <li key={job.id}>
              <button
                type="button"
                aria-pressed={selectedJobId === job.id}
                onClick={() => onSelect(job.id)}
              >
                {job.id} — {job.state}
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </section>
  );
}
