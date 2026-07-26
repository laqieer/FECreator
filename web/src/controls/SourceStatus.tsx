import { useEffect, useState, type ChangeEvent } from "react";
import type { SourcePlan } from "../api/types";

export interface SourceStatusProps {
  jobId: string | null;
  plan: SourcePlan | null;
  loading: boolean;
  error: string | null;
  onPlan: () => void;
  onSubmit: (files: File[]) => void;
}

export function SourceStatus({
  jobId,
  plan,
  loading,
  error,
  onPlan,
  onSubmit,
}: SourceStatusProps) {
  const [files, setFiles] = useState<File[]>([]);

  useEffect(() => {
    setFiles([]);
  }, [jobId]);

  const handleFiles = (event: ChangeEvent<HTMLInputElement>) => {
    setFiles(Array.from(event.target.files ?? []));
  };

  if (jobId === null) {
    return (
      <section aria-label="source-status">
        <h2>Sources</h2>
        <p>Create or select a job to plan sources.</p>
      </section>
    );
  }

  return (
    <section aria-label="source-status">
      <h2>Sources for {jobId}</h2>
      <button type="button" disabled={loading} onClick={onPlan}>
        Plan sources
      </button>
      {loading ? <p role="status">Updating sources…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {plan ? (
        <>
          <p>{plan.background_contract}</p>
          <ul aria-label="source-prompts">
            {plan.prompts.map((prompt) => (
              <li key={prompt}>{prompt}</li>
            ))}
          </ul>
          <label>
            Source files
            <input key={jobId} type="file" multiple onChange={handleFiles} />
          </label>
          <button type="button" disabled={loading || files.length === 0} onClick={() => onSubmit(files)}>
            Submit sources
          </button>
        </>
      ) : (
        <p>Plan sources before submitting local files.</p>
      )}
    </section>
  );
}
