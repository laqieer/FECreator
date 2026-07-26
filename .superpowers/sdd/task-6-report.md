# Task 6 Report: Review-Gated Final Publication

## Status

Implemented, verified, committed, and pushed.

## RED / GREEN Evidence

- **RED:** `pytest -q tests/jobs/test_model.py tests/jobs/test_service.py
  tests/jobs/test_approvals.py tests/app/test_app.py tests/portrait/test_build_e2e.py
  tests/reporting/test_json_report.py tests/reporting/test_bundle.py` failed with the expected
  missing `parent_candidate_id`, `discard_pending`, review lifecycle, and finalization APIs.
- **RED:** focused report/retry-lineage tests failed because `build_report()` had no approval
  parameter and retry candidates had no rejected-candidate parent.
- **RED:** a threaded regression test reproduced a generic approval appending between a rejected
  approval record and its failed-event rollback.
- **GREEN:** all focused job, app, portrait, reporting, and lineage suites passed after the
  implementation and concurrency repair.

## Lifecycle and Publication

- Jobs persist optional `parent_candidate_id`; a retry creates one new `created` job linked to
  `<rejected_job_id>-candidate`, and its generated candidate lineage has that same parent.
- Candidate approval logs a reviewer event. Rejection atomically writes the candidate decision,
  emits a reviewer event, and transitions `waiting_for_review -> failed`; it preserves candidate
  artifacts. A second review decision, rejection, retry, or finalization fails explicitly.
- Finalization requires candidate approval, strictly revalidates `candidate/package`, then
  transitions `waiting_for_review -> validating -> completed`. It publishes root `package`,
  `report.json`, `lineage.json`, and `bundle`, plus `<job_id>-export`, whose sole parent is
  `<job_id>-candidate` and whose `approved_by` is the reviewer.

## Locking and Rollback

- Review and generic approval writes use the job lock before the approval-file lock; review events
  follow that order. This guarantees `discard_pending()` can remove only its exact trailing
  approval record while the transaction is active.
- Retry serializes on the rejected job lock. Finalization loads candidate, approval, and lineage
  before taking its transition lock, then stages privately and publishes under the job lock before
  taking bundle and lineage locks. No path takes those locks in reverse.
- Root artifacts are staged, tracked individually, and rolled back in reverse with the export
  lineage on event/persistence failure. Candidate evidence is never removed. Cleanup failures
  propagate; retry cleanup now also surfaces deletion failures.

## Verification

- `ruff check .` — passed
- `ruff format --check .` — passed
- `mypy src` — passed (83 source files)
- Focused Task 6 suites — passed
- `pytest -q` — passed; only the pre-existing Starlette `TestClient` deprecation warning appeared.

## Files and Review

- Added `assets/portrait/publication.py`; updated job persistence/service/approval logic, app
  facade, candidate lineage construction, report/bundle approval serialization, and lifecycle
  tests.
- Self-review and an independent code review found an approval-tail rollback race. It was fixed
  by serializing all facade approval writes through the job lock and covered by a threaded
  regression test.
- Deviation: `candidate.py` was also changed so retry candidate lineage records the rejected
  parent, as required by the accepted review-lifecycle design.

## Commit and Push

- Code commit: `f292dd8 feat: require review before portrait publication`
- Pushed to `origin/issue-1-completion`.

## Concerns

No open functional concerns. The full suite reports the existing dependency deprecation warning
from Starlette's `TestClient`.
