import { useCallback, useEffect, useRef, useState } from "react";
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
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [action, setAction] = useState<WorkbenchAction>("idle");
  const selectedJobIdRef = useRef<string | null>(null);
  const jobEvents = useJobEvents(selectedJobId ?? "", events);

  const refreshJobs = useCallback(async () => {
    setAction("loading");
    try {
      const next = sortJobs(await api.listJobs());
      setJobs(next);
      setSelectedJobId((current) => {
        const selected = current ?? next[0]?.id ?? null;
        selectedJobIdRef.current = selected;
        return selected;
      });
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
      try {
        const job = await api.getJob(jobId);
        if (selectedJobIdRef.current !== jobId) {
          return;
        }
        setSelectedJob(job);
        setJobs((current) => replaceJob(current, job));
        try {
          const nextCandidate = await api.getJobCandidate(jobId);
          if (selectedJobIdRef.current === jobId) {
            setCandidate(nextCandidate);
          }
        } catch {
          if (selectedJobIdRef.current === jobId) {
            setCandidate(null);
          }
        }
      } catch (cause) {
        if (selectedJobIdRef.current === jobId) {
          setSelectedJob(null);
          setCandidate(null);
          setError(toErrorMessage(cause));
        }
      } finally {
        if (selectedJobIdRef.current === jobId) {
          setAction("idle");
        }
      }
    },
    [api],
  );

  useEffect(() => {
    void refreshJobs();
  }, [refreshJobs]);

  useEffect(() => {
    if (selectedJobId === null) {
      selectedJobIdRef.current = null;
      setSelectedJob(null);
      setCandidate(null);
      return;
    }
    void loadSelectedJob(selectedJobId);
  }, [loadSelectedJob, selectedJobId]);

  useEffect(() => {
    if (selectedJobId !== null && jobEvents.events.length > 0) {
      void (async () => {
        await refreshJobs();
        if (selectedJobIdRef.current === selectedJobId) {
          await loadSelectedJob(selectedJobId);
        }
      })();
    }
  }, [jobEvents.events, loadSelectedJob, refreshJobs, selectedJobId]);

  const selectJob = useCallback((jobId: string) => {
    selectedJobIdRef.current = jobId;
    setSelectedJobId(jobId);
    setSelectedJob(null);
    setCandidate(null);
    setSourcePlan(null);
    setSourceError(null);
  }, []);

  const createJob = useCallback(
    async (manifest: Manifest) => {
      setAction("creating");
      try {
        const job = await api.createJob(manifest);
        setJobs((current) => replaceJob(current, job));
        selectedJobIdRef.current = job.id;
        setSelectedJobId(job.id);
        setSourcePlan(null);
        setSourceError(null);
        setError(null);
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
    try {
      const plan = await api.planSources(selectedJobId);
      if (selectedJobIdRef.current !== selectedJobId) {
        return;
      }
      setSourcePlan(plan);
      setSourceError(null);
      await refreshJobs();
      await loadSelectedJob(selectedJobId);
    } catch (cause) {
      if (selectedJobIdRef.current === selectedJobId) {
        setSourceError(toErrorMessage(cause));
      }
    } finally {
      if (selectedJobIdRef.current === selectedJobId) {
        setAction("idle");
      }
    }
  }, [api, loadSelectedJob, refreshJobs, selectedJobId]);

  const submitSources = useCallback(
    async (files: File[]) => {
      if (selectedJobId === null) {
        return;
      }
      setAction("submitting-sources");
      try {
        const job = await api.submitSources(selectedJobId, files);
        if (selectedJobIdRef.current !== selectedJobId) {
          return;
        }
        setJobs((current) => replaceJob(current, job));
        setSelectedJob(job);
        setSourceError(null);
        try {
          const nextCandidate = await api.getJobCandidate(job.id);
          if (selectedJobIdRef.current === selectedJobId) {
            setCandidate(nextCandidate);
          }
        } catch {
          if (selectedJobIdRef.current === selectedJobId) {
            setCandidate(null);
          }
        }
        await refreshJobs();
      } catch (cause) {
        if (selectedJobIdRef.current === selectedJobId) {
          setSourceError(toErrorMessage(cause));
        }
      } finally {
        if (selectedJobIdRef.current === selectedJobId) {
          setAction("idle");
        }
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
    sourceError,
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
