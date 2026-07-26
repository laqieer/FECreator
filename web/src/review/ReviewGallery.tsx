import { useEffect, useRef, useState } from "react";
import type { ApprovalRecord } from "../api/types";
import { clipRectToBounds, rectToPercentages, type Rect } from "./cropMath";

export interface ReviewCandidate {
  id: string;
  src: string;
  imageWidth: number;
  imageHeight: number;
  cropRect: Rect;
  specRect: Rect;
}

interface ReviewGalleryProps {
  candidates: ReviewCandidate[];
  onApprove: (id: string) => void | Promise<void>;
  onReject: (id: string, reason: string) => void | Promise<void>;
  onFinalize?: () => void | Promise<void>;
  onRetry?: () => void | Promise<void>;
  approvals?: ApprovalRecord[] | null;
  approvalsError?: string | null;
  pendingAction?: "approve" | "reject" | "finalize" | "retry" | null;
  error?: string | null;
}

export function ReviewGallery({
  candidates,
  onApprove,
  onReject,
  onFinalize,
  onRetry,
  approvals = null,
  approvalsError = null,
  pendingAction = null,
  error = null,
}: ReviewGalleryProps) {
  const [rejectionReasons, setRejectionReasons] = useState<Record<string, string>>({});
  const [validationError, setValidationError] = useState<string | null>(null);
  const previousError = useRef<string | null>(error);
  const disabled = pendingAction !== null;
  const latestApproval = approvals?.at(-1);

  useEffect(() => {
    if (error !== previousError.current) {
      previousError.current = error;
      if (error !== null) {
        setValidationError(null);
      }
    }
  }, [error]);

  const approve = (candidateId: string) => {
    setValidationError(null);
    void onApprove(candidateId);
  };

  const reject = (candidateId: string) => {
    const reason = rejectionReasons[candidateId]?.trim() ?? "";
    if (reason === "") {
      setValidationError("A rejection reason is required.");
      return;
    }
    setValidationError(null);
    void onReject(candidateId, reason);
  };

  return (
    <section aria-label="review-gallery">
      <h2>Candidate review</h2>
      {pendingAction ? <p role="status">Review action in progress: {pendingAction}.</p> : null}
      {validationError ?? error ? <p role="alert">{validationError ?? error}</p> : null}
      {approvalsError ? (
        <p role="alert">Unable to load the review history: {approvalsError}</p>
      ) : approvals === null ? null : latestApproval ? (
        <p>
          Latest review: {latestApproval.decision} by {latestApproval.actor}.
          {latestApproval.reason ? ` Reason: ${latestApproval.reason}` : ""}
        </p>
      ) : (
        <p>No review decisions recorded.</p>
      )}
      {candidates.length === 0 ? (
        <p>No review candidates available.</p>
      ) : (
        <ul aria-label="candidate-list">
          {candidates.map((candidate) => {
            const bounds = { width: candidate.imageWidth, height: candidate.imageHeight };
            const cropRect = rectToPercentages(clipRectToBounds(candidate.cropRect, bounds), bounds);
            const specRect = rectToPercentages(clipRectToBounds(candidate.specRect, bounds), bounds);

            return (
              <li key={candidate.id}>
                <figure>
                  <div
                    style={{
                      position: "relative",
                      display: "inline-block",
                      width: candidate.imageWidth,
                      height: candidate.imageHeight,
                      border: "1px solid currentColor",
                      overflow: "hidden",
                    }}
                  >
                    <img
                      src={candidate.src}
                      alt={`Candidate ${candidate.id}`}
                      width={candidate.imageWidth}
                      height={candidate.imageHeight}
                    />
                    <div
                      aria-label={`crop-overlay-${candidate.id}`}
                      style={{
                        position: "absolute",
                        border: "2px dashed #d22",
                        pointerEvents: "none",
                        ...cropRect,
                      }}
                    />
                    <div
                      aria-label={`spec-overlay-${candidate.id}`}
                      style={{
                        position: "absolute",
                        border: "2px solid #2f6fed",
                        pointerEvents: "none",
                        ...specRect,
                      }}
                    />
                  </div>
                  <figcaption>{candidate.id}</figcaption>
                </figure>
                <div>
                  <button type="button" disabled={disabled} onClick={() => approve(candidate.id)}>
                    Approve {candidate.id}
                  </button>
                  <label>
                    Rejection reason for {candidate.id}
                    <input
                      value={rejectionReasons[candidate.id] ?? ""}
                      onChange={(event) => {
                        setValidationError(null);
                        setRejectionReasons((current) => ({
                          ...current,
                          [candidate.id]: event.target.value,
                        }));
                      }}
                    />
                  </label>
                  <button type="button" disabled={disabled} onClick={() => reject(candidate.id)}>
                    Reject {candidate.id}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <div>
        <button type="button" disabled={disabled || onFinalize === undefined} onClick={() => void onFinalize?.()}>
          Finalize review
        </button>
        <button type="button" disabled={disabled || onRetry === undefined} onClick={() => void onRetry?.()}>
          Retry job
        </button>
      </div>
    </section>
  );
}
