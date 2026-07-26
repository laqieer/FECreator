import { useCallback, useEffect, useRef, useState } from "react";
import type { ApiClient } from "../api/client";
import type { ApprovalRecord, CandidateSnapshot, Job, Manifest, SourcePlan } from "../api/types";
import type { JobEventSource } from "../jobs/eventSource";
import { useJobEvents } from "../jobs/useJobEvents";

type WorkbenchAction =
  | "idle"
  | "creating"
  | "loading"
  | "planning-sources"
  | "submitting-sources"
  | "approving"
  | "rejecting"
  | "finalizing"
  | "retrying";

function toErrorMessage(cause: unknown): string {
  return cause instanceof Error ? cause.message : "The requested workbench action failed.";
}

function finalizationError(diagnostics: { code: string; message: string }[]): Error {
  const message = diagnostics.map((diagnostic) => `${diagnostic.code}: ${diagnostic.message}`).join(" ");
  return new Error(message || "Finalization did not complete.");
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
  const [approvals, setApprovals] = useState<ApprovalRecord[]>([]);
  const [sourcePlan, setSourcePlan] = useState<SourcePlan | null>(null);
  const [sourceError, setSourceError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
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
        try {
          const nextApprovals = await api.listApprovals(jobId);
          if (selectedJobIdRef.current === jobId) {
            setApprovals(nextApprovals);
          }
        } catch {
          if (selectedJobIdRef.current === jobId) {
            setApprovals([]);
          }
        }
      } catch (cause) {
        if (selectedJobIdRef.current === jobId) {
          setSelectedJob(null);
          setCandidate(null);
          setApprovals([]);
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
      setApprovals([]);
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
    setApprovals([]);
    setSourcePlan(null);
    setSourceError(null);
    setActionError(null);
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
        setActionError(null);
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

  const refreshSelectedJob = useCallback(
    async (jobId = selectedJobId) => {
      if (jobId === null) {
        return;
      }
      await refreshJobs();
      if (selectedJobIdRef.current === jobId) {
        await loadSelectedJob(jobId);
      }
    },
    [loadSelectedJob, refreshJobs, selectedJobId],
  );

  const approveReview = useCallback(
    async (actor: string) => {
      if (selectedJobId === null) {
        return;
      }
      const jobId = selectedJobId;
      setAction("approving");
      setActionError(null);
      try {
        await api.approveReview(jobId, actor);
        await refreshSelectedJob(jobId);
      } catch (cause) {
        if (selectedJobIdRef.current === jobId) {
          setActionError(toErrorMessage(cause));
        }
      } finally {
        if (selectedJobIdRef.current === jobId) {
          setAction("idle");
        }
      }
    },
    [api, refreshSelectedJob, selectedJobId],
  );

  const rejectReview = useCallback(
    async (actor: string, reason: string) => {
      if (selectedJobId === null) {
        return;
      }
      const jobId = selectedJobId;
      setAction("rejecting");
      setActionError(null);
      try {
        await api.rejectReview(jobId, actor, reason);
        await refreshSelectedJob(jobId);
      } catch (cause) {
        if (selectedJobIdRef.current === jobId) {
          setActionError(toErrorMessage(cause));
        }
      } finally {
        if (selectedJobIdRef.current === jobId) {
          setAction("idle");
        }
      }
    },
    [api, refreshSelectedJob, selectedJobId],
  );

  const finalizeJob = useCallback(async () => {
    if (selectedJobId === null) {
      return;
    }
    const jobId = selectedJobId;
    setAction("finalizing");
    setActionError(null);
    try {
      const result = await api.finalizeJob(jobId);
      if (!result.ok) {
        throw finalizationError(result.diagnostics);
      }
      await refreshSelectedJob(jobId);
    } catch (cause) {
      if (selectedJobIdRef.current === jobId) {
        setActionError(toErrorMessage(cause));
      }
    } finally {
      if (selectedJobIdRef.current === jobId) {
        setAction("idle");
      }
    }
  }, [api, refreshSelectedJob, selectedJobId]);

  const retryJob = useCallback(
    async (actor: string) => {
      if (selectedJobId === null) {
        return;
      }
      const jobId = selectedJobId;
      let refreshedJobId = jobId;
      setAction("retrying");
      setActionError(null);
      try {
        const retry = await api.retryJob(jobId, actor);
        refreshedJobId = retry.id;
        selectedJobIdRef.current = retry.id;
        setSelectedJobId(retry.id);
        setSelectedJob(retry);
        setCandidate(null);
        setApprovals([]);
        await refreshJobs();
        await loadSelectedJob(retry.id);
      } catch (cause) {
        if (selectedJobIdRef.current === refreshedJobId) {
          setActionError(toErrorMessage(cause));
        }
      } finally {
        setAction("idle");
      }
    },
    [api, loadSelectedJob, refreshJobs, selectedJobId],
  );

  return {
    jobs,
    selectedJobId,
    selectedJob,
    candidate,
    approvals,
    sourcePlan,
    sourceError,
    error,
    actionError,
    action,
    events: jobEvents,
    selectJob,
    refreshJobs,
    refreshSelectedJob,
    createJob,
    planSources,
    submitSources,
    approveReview,
    rejectReview,
    finalizeJob,
    retryJob,
  };
}
