interface Candidate {
  id: string;
  src: string;
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
          {candidates.map((candidate) => (
            <li key={candidate.id}>
              <figure>
                <div
                  style={{
                    position: "relative",
                    display: "inline-block",
                    border: "1px solid currentColor",
                  }}
                >
                  <img src={candidate.src} alt={`Candidate ${candidate.id}`} />
                  <div
                    aria-label={`crop-overlay-${candidate.id}`}
                    style={{
                      position: "absolute",
                      inset: "12% 16%",
                      border: "2px dashed #d22",
                      pointerEvents: "none",
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
          ))}
        </ul>
      )}
    </section>
  );
}
