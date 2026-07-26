import { useCallback, useEffect, useState } from "react";
import type { ApiClient } from "../api/client";
import type { CandidateSnapshot, Job, Manifest, SourcePlan } from "../api/types";
import type { JobEventSource } from "../jobs/eventSource";
import { useJobEvents } from "../jobs/useJobEvents";

type WorkbenchAction = "idle" | "creating" | "loading" | "planning-sources" | "submitting-sources";

function toErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The requested workbench action failed.";
}

function sortJobs(jobs: Job[]): Job[] {
  return [...jobs].sort((left, right) => left.id.localeCompare(right.id));
}

function replaceJob(jobs: Job[], nextJob: Job): Job[] {
  return sortJobs([...jobs.filter((job) => job.id !== nextJob.id), nextJob]);
}

export function useWorkbench(api: ApiClient, events: JobEventSource) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);
  const [selectedJob, setSelectedJob] = useState<Job | null>(null);
  const [candidate, setCandidate] = useState<CandidateSnapshot | null>(null);
  const [sourcePlan, setSourcePlan] = useState<SourcePlan | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<WorkbenchAction>("idle");
  const jobEvents = useJobEvents(selectedJobId ?? "", events);

  const refreshJobs = useCallback(async () => {
    setAction("loading");
    try {
      const next = sortJobs(await api.listJobs());
      setJobs(next);
      setSelectedJobId((current) => current ?? next[0]?.id ?? null);
      setError(null);
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setAction("idle");
    }
  }, [api]);

  const loadSelectedJob = useCallback(
    async (jobId: string) => {
      setAction("loading");
      setError(null);
      setSourcePlan(null);
      try {
        const job = await api.getJob(jobId);
        setSelectedJob(job);
        setJobs((current) => replaceJob(current, job));
        try {
          setCandidate(await api.getJobCandidate(jobId));
        } catch {
          setCandidate(null);
        }
      } catch (cause) {
        setSelectedJob(null);
        setCandidate(null);
        setError(toErrorMessage(cause));
      } finally {
        setAction("idle");
      }
    },
    [api],
  );

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (selectedJobId === null) {
      setSelectedJob(null);
      setCandidate(null);
      return;
    }
    void loadSelectedJob(selectedJobId);
  }, [loadSelectedJob, selectedJobId]);

  useEffect(() => {
    if (selectedJobId !== null && jobEvents.events.length > 0) {
      void refreshJobs();
    }
  }, [jobEvents.events, refreshJobs, selectedJobId]);

  const selectJob = useCallback((jobId: string) => {
    setSelectedJobId(jobId);
  }, []);

  const createJob = useCallback(
    async (manifest: Manifest) => {
      setAction("creating");
      setError(null);
      try {
        const job = await api.createJob(manifest);
        setJobs((current) => replaceJob(current, job));
        setSelectedJobId(job.id);
      } catch (cause) {
        setError(toErrorMessage(cause));
      } finally {
        setAction("idle");
      }
    },
    [api],
  );

  const planSources = useCallback(async () => {
    if (selectedJobId === null) {
      return;
    }
    setAction("planning-sources");
    setError(null);
    try {
      setSourcePlan(await api.planSources(selectedJobId));
      await refreshJobs();
    await loadSelectedJob(selectedJobId);
    } catch (cause) {
      setError(toErrorMessage(cause));
    } finally {
      setAction("idle");
    }
  }, [api, refreshJobs, selectedJobId]);

  const submitSources = useCallback(
    async (files: File[]) => {
      if (selectedJobId === null) {
        return;
      }
      setAction("submitting-sources");
      setError(null);
      try {
        const job = await api.submitSources(selectedJobId, files);
        setJobs((current) => replaceJob(current, job));
        setSelectedJob(job);
        try {
          setCandidate(await api.getJobCandidate(job.id));
        } catch {
          setCandidate(null);
        }
        await refreshJobs();
      } catch (cause) {
        setError(toErrorMessage(cause));
      } finally {
        setAction("idle");
      }
    },
    [api, refreshJobs, selectedJobId],
  );

  return {
    jobs,
    selectedJobId,
    selectedJob,
    candidate,
    sourcePlan,
    error,
    action,
    events: jobEvents,
    selectJob,
    refreshJobs,
    createJob,
    planSources,
    submitSources,
  };
}
