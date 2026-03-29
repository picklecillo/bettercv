# Plan: Multi-JD Comparison

> Source PRD: docs/multi_jd_compare_prd.md

## Architectural decisions

- **New `compare` Django app** — fully separate from `analyzer` and `coach`. Registered in `INSTALLED_APPS`, routes included under `/compare/`.
- **Navigation** — header updated to include a third nav link: "Compare" at `/compare/`.
- **Routes**:
  - `GET /compare/` — resume input form; clears `session["compare"]`
  - `POST /compare/parse-resume/` — store resume in session, swap `<main>` to workspace
  - `POST /compare/add-jd/` — validate count (max 10), create JD slot, return card + SSE container (`beforeend` into cards area)
  - `GET /compare/stream/?key=<nonce>` — pop nonce, stream analysis, extract metadata, emit `metadata` event, commit to session
  - `POST /compare/remove-jd/` — remove JD slot from session, return empty 200
- **Session schema**:
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
  `jd_id` is a UUID. Max 10 entries enforced at `POST /compare/add-jd/`.
- **Key models**: `JDMetadata` — dataclass `{company: str, title: str, score_low: int, score_high: int}`
- **Service layer**: `CompareService` with `stream_analysis(resume_text, jd_text) → Iterator[str]` and `extract_metadata(analysis_text) → JDMetadata`. Takes injected `anthropic.Anthropic` client. `get_compare_service()` factory for production wiring.
- **Exceptions**: `CompareMetadataError` — raised when `extract_metadata()` receives no tool use block. Surfaced as a `—` score in the table row; does not prevent the analysis card from rendering.
- **Nonce pattern**: same use-once UUID key as `coach` — `POST /compare/add-jd/` stores `{jd_id, resume_text, jd_text}` under `session[nonce]`; stream endpoint pops it before streaming.
- **Shared utilities**: `analyzer/pdf.py` imported directly in `compare/views.py`.

---

## Phase 1: Resume Input and Workspace

**User stories**: 1, 2, 14, 15, 16

### What to build

`GET /compare/` clears any existing `session["compare"]` and renders a resume input form (paste textarea + PDF upload, same pattern as the ATS Analyzer and Resume Coach). `POST /compare/parse-resume/` extracts the resume text (PDF takes priority over paste), stores it in `session["compare"]`, and swaps `<main>` to the comparison workspace. The workspace shows: a persistent summary table (initially empty, with column headers), an empty cards area, and an "Add a job description" form. Navigation is updated with a "Compare" link in the header of all three tools.

If no input is provided, or the PDF is unreadable, a styled error div is returned instead.

### Acceptance criteria

- [ ] `GET /compare/` returns 200 with a resume input form (paste + PDF upload)
- [ ] `GET /compare/` clears any existing `session["compare"]`
- [ ] `POST /compare/parse-resume/` with pasted text swaps `<main>` to the workspace
- [ ] `POST /compare/parse-resume/` with a PDF extracts text and returns the same
- [ ] PDF upload takes priority over pasted text when both are submitted
- [ ] Submitting neither returns an error div
- [ ] An unreadable PDF surfaces a `PdfExtractionError` as an error div
- [ ] `session["compare"]["resume_text"]` is set after a successful parse
- [ ] The workspace shows an empty summary table, an empty cards area, and a JD input form
- [ ] Navigation header on all three tools includes a "Compare" link to `/compare/`
- [ ] `compare` app routes are registered under `/compare/` and do not touch existing routes

---

## Phase 2: Add JD, Streaming Analysis, and Score Extraction

**User stories**: 3, 4, 5, 6, 7, 8, 9, 13

### What to build

`POST /compare/add-jd/` validates that the session has a resume and that fewer than 10 JDs exist, generates a `jd_id` and nonce, stores both in session, and returns two fragments: a new row in the summary table (status: "Analyzing…") and an analysis card with an SSE container — both appended via `beforeend`.

`GET /compare/stream/` pops the nonce, streams the analysis via `CompareService.stream_analysis()` as `chunk` SSE events, accumulates the full text, then calls `CompareService.extract_metadata()`. On success, commits `{analysis, metadata}` to `session["compare"]["jds"][jd_id]` via `session.save()` and emits a `metadata` SSE event that HTMX uses to swap the summary table row with the real score range and `company · title` label. On metadata failure, commits the analysis text only and emits an error `metadata` event (row shows `—`). The stream always ends with a `done` event.

`CompareService.stream_analysis()` reuses the same system prompt and model as the existing ATS analyzer. `CompareService.extract_metadata()` uses Claude tool use with a forced `extract_jd_metadata` tool call.

### Acceptance criteria

- [ ] `POST /compare/add-jd/` with a JD returns a summary table row and an analysis card with SSE container
- [ ] `POST /compare/add-jd/` with no resume in session returns an error div
- [ ] `POST /compare/add-jd/` with missing JD text returns an error div
- [ ] The summary table row shows "Analyzing…" while the stream is active
- [ ] Analysis text streams into the card word by word via SSE `chunk` events
- [ ] After streaming, `extract_metadata()` is called and a `metadata` SSE event is emitted
- [ ] The summary table row updates to show `company · title` and ATS score range on metadata success
- [ ] On metadata failure, the row shows `—` and the analysis card still renders
- [ ] `session["compare"]["jds"][jd_id]` contains `analysis` and `metadata` after a successful stream
- [ ] Errored streams are not committed to session
- [ ] Missing or expired nonce returns 400
- [ ] `CompareService.stream_analysis()` is tested: chunks yielded, resume + JD text passed to API
- [ ] `CompareService.extract_metadata()` is tested: valid analysis returns `JDMetadata`, missing tool use block raises `CompareMetadataError`
- [ ] View tests cover: successful add+stream+metadata cycle, metadata failure, stream error

---

## Phase 3: Remove JD and Limit Guard

**User stories**: 10, 11, 12

### What to build

`POST /compare/remove-jd/` receives a `jd_id`, removes `session["compare"]["jds"][jd_id]`, and returns an empty 200. HTMX removes the corresponding analysis card and summary table row from the DOM client-side (via `hx-target` + `hx-swap="delete"`).

`POST /compare/add-jd/` enforces a maximum of 10 JDs: if `len(session["compare"]["jds"]) >= 10`, it returns a styled error div explaining the limit instead of adding a new slot.

### Acceptance criteria

- [ ] `POST /compare/remove-jd/` with a valid `jd_id` removes the slot from session and returns 200
- [ ] `POST /compare/remove-jd/` with an unknown `jd_id` returns 400
- [ ] Removing a JD removes its card and summary table row from the DOM
- [ ] Removing one JD does not affect any other JD's card or table row
- [ ] `POST /compare/add-jd/` with 10 JDs already present returns an error div
- [ ] Adding an 11th JD does not create a session slot
- [ ] View tests cover: successful remove, unknown jd_id, limit enforcement
