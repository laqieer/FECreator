import { clipRectToBounds, rectToPercentages, type Rect } from "./cropMath";

interface Candidate {
  id: string;
  src: string;
  imageWidth: number;
  imageHeight: number;
  cropRect: Rect;
  specRect: Rect;
}

interface ReviewGalleryProps {
  candidates: Candidate[];
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}

export function ReviewGallery({ candidates, onApprove, onReject }: ReviewGalleryProps) {
  return (
    <section aria-label="review-gallery">
      <h2>Candidate review</h2>
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
                  <button type="button" onClick={() => onApprove(candidate.id)}>
                    Approve {candidate.id}
                  </button>
                  <button type="button" onClick={() => onReject(candidate.id)}>
                    Reject {candidate.id}
                  </button>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
