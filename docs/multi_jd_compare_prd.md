# PRD: Multi-JD Comparison

## Problem Statement

Job seekers applying to multiple roles must run separate ATS analyses for each job description, manually switching between tabs and mentally tracking which resume performed best against which role. There is no way to compare results side by side, rank opportunities, or identify which job is the best fit in a single view.

## Solution

A dedicated Compare workspace at `/compare/` where the user uploads their resume once, then adds up to 10 job descriptions one at a time. Each JD triggers an immediate streaming ATS analysis. A persistent summary table at the top of the page shows the extracted ATS score range and job label (company · title) for every completed analysis, giving the user a ranked at-a-glance view. Full analysis cards are stacked below the table. JDs can be removed individually.

## User Stories

1. As a job seeker, I want to upload my resume once and analyze it against multiple job descriptions, so that I don't have to re-enter my CV for each role.
2. As a job seeker, I want to paste or upload a PDF resume, so that I can start comparing without manual re-entry.
3. As a job seeker, I want to add job descriptions one at a time, so that I can start seeing results immediately without waiting to collect all JDs first.
4. As a job seeker, I want each analysis to stream in word by word as I add a JD, so that I get immediate feedback.
5. As a job seeker, I want the app to automatically extract the company name and job title from each JD, so that I don't have to label them manually.
6. As a job seeker, I want a summary table showing the ATS score and job label for every completed analysis, so that I can compare results at a glance without scrolling through full cards.
7. As a job seeker, I want the summary table to update automatically when each analysis finishes, so that the scores appear without any manual action.
8. As a job seeker, I want the summary table to show a pending indicator while an analysis is still streaming, so that I know results are on the way.
9. As a job seeker, I want to see the full ATS analysis for each JD in a stacked card below the summary table, so that I can read the detailed breakdown for any role.
10. As a job seeker, I want to be able to remove a JD card I no longer need, so that I can keep the workspace tidy.
11. As a job seeker, I want removing a card to also remove its row from the summary table, so that the table stays accurate.
12. As a job seeker, I want a clear error if I try to add more than 10 JDs, so that I understand the limit.
13. As a job seeker, I want to see a clear error if a JD submission fails, so that I can try again.
14. As a job seeker, I want the Compare tool accessible from the site navigation, so that I can find it without knowing the URL.
15. As a job seeker, I want navigating to `/compare/` to clear any previous compare session, so that I always start fresh.
16. As a job seeker, I want an unreadable PDF to surface a clear error, so that I understand what went wrong.

## Implementation Decisions

### App structure
- New `compare` Django app, fully separate from `analyzer` and `coach`.
- Navigation header updated to include a third link: "Compare".
- `GET /compare/` clears any existing `session["compare"]` and renders the resume input form.

### Routes
- `GET /compare/` — resume input form; clears compare session
- `POST /compare/parse-resume/` — extracts resume text (PDF or paste), stores in session, swaps `<main>` to the comparison workspace
- `POST /compare/add-jd/` — validates JD count (max 10), creates a JD slot in session, returns an analysis card fragment with SSE container (`beforeend` into the cards area)
- `GET /compare/stream/?key=<nonce>` — pops nonce, streams analysis chunks, then calls `CompareService.extract_metadata()` and emits a `metadata` SSE event; HTMX swaps the summary table row for that JD
- `POST /compare/remove-jd/` — removes the JD slot from session, returns empty 200; HTMX removes the card and table row from the DOM

### Session schema
```
session["compare"] = {
  "resume_text": str,
  "jds": {
    "<jd_id>": {
      "jd_text": str,
      "analysis": str | None,
      "metadata": {"company": str, "title": str, "score_low": int, "score_high": int} | None
    }
  }
}
```
`jd_id` is a UUID generated when the JD is added. Max 10 entries enforced at `POST /compare/add-jd/`.

### Service layer — `CompareService`
Two methods, injected `anthropic.Anthropic` client, `get_compare_service()` factory:

- `stream_analysis(resume_text, jd_text) → Iterator[str]` — identical system prompt and model to the existing ATS analyzer; streams text chunks
- `extract_metadata(analysis_text) → JDMetadata` — non-streaming tool use call on the completed analysis text; forces a single `extract_jd_metadata` tool call returning `{company, title, score_low, score_high}`; raises `CompareMetadataError` if the tool use block is missing

### Key models
`JDMetadata` — dataclass `{company: str, title: str, score_low: int, score_high: int}`

### Streaming and metadata flow
- Nonce-per-POST pattern (same as coach): `POST /compare/add-jd/` generates a UUID nonce, stores `{jd_id, resume_text, jd_text}` under `session[nonce]`.
- `GET /compare/stream/` pops the nonce, streams analysis chunks as `chunk` SSE events, then calls `extract_metadata()` on the accumulated text.
- On metadata success: commits `{analysis, metadata}` to `session["compare"]["jds"][jd_id]` via `session.save()`, emits a `metadata` SSE event; HTMX swaps the summary table row from `—` to the real score and label.
- On metadata failure: emits an error `metadata` event with a `—` score; analysis text is still committed.
- `done` SSE event closes the connection.
- Partial/errored streams are not committed to session history.

### Summary table
- Always visible in the workspace, one row per JD added.
- Columns: Label (company · title) | ATS Score | Status
- Row is added when the JD card is inserted (status: Analyzing…).
- Row is swapped via the `metadata` SSE event when the analysis completes.
- Remove button on each row triggers `POST /compare/remove-jd/`.

### Exceptions
- `CompareMetadataError` — raised when `extract_metadata()` receives no tool use block. Surfaced as a `—` score in the table row; does not prevent the analysis card from rendering.

### Shared utilities
- `analyzer/pdf.py` — imported directly in `compare/views.py`, same pattern as `coach`.
- Same `ClaudeService` system prompt is reused verbatim in `CompareService.stream_analysis()`.

## Testing Decisions

- Tests follow the existing pattern: `FakeCompareService` injected via `patch("compare.views.get_compare_service", ...)`.
- `CompareService` tested directly with `MagicMock(spec=anthropic.Anthropic)` — no module-level patching.
- Test `stream_analysis` for: chunks yielded, resume and JD text passed to API.
- Test `extract_metadata` for: valid analysis returns correct `JDMetadata`, missing tool use block raises `CompareMetadataError`.
- Test views for: resume parse (text and PDF, PDF priority, neither → error), add JD returns SSE card, max-10 guard returns error, stream commits analysis + metadata, metadata failure still commits analysis, remove JD clears session slot, missing/expired nonce returns 400.
- Do not test Claude prompt wording — test behaviour at module boundaries only.
- Tests go in `compare/tests/test_compare_service.py` and `compare/tests/test_views.py`.

## Out of Scope

- Sorting or ranking the summary table by score.
- Editing a JD after it has been submitted.
- Re-running an analysis without removing and re-adding the card.
- Persisting compare sessions across page refreshes or browser sessions.
- Connecting compare results to the Resume Coach flow.
- User accounts or authentication.
- Exporting the comparison as a document.

## Further Notes

- `CompareService` and `ClaudeService` are sibling classes — `CompareService` reuses the same system prompt and model but adds `extract_metadata()`. No inheritance.
- The `/compare/` URL namespace is separate from `/analyze/` and `/coach/`; no existing routes are modified.
- `session["compare"]` is separate from the coach and analyzer session keys.
- The `extract_metadata()` tool use call is a second API call made after the stream completes — it adds latency before the score appears in the table, but keeps the streaming and extraction concerns cleanly separated.
