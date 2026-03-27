# Plan: ATS Analyzer V1

> Source PRD: `docs/ats_analyzer_spec.md`

## Architectural decisions

- **Routes**: `GET /` — form view; `POST /analyze/` — SSE streaming endpoint
- **Streaming**: Server-Sent Events via `hx-ext="sse"` from day one (not plain `StreamingHttpResponse`)
- **Models**: None — V1 is fully stateless, SQLite only for Django internals
- **Claude model**: `claude-sonnet-4-20250514`, max_tokens 2000
- **Resume input**: PDF upload takes priority over pasted text; mutually exclusive at the view level
- **Markdown rendering**: Server-side, after full response is accumulated (streamed as plain text, rendered at end)

---

## Phase 1: Project scaffold + form renders

**User stories**: User can load the app and see the input form

### What to build

Bootstrap the Django project and `analyzer` app. Wire `GET /` to a view that renders the form template. Load HTMX and the SSE extension via CDN. Include the result div. No form submission behavior yet — the goal is a fully runnable stack with a visible UI.

### Acceptance criteria

- [ ] `python manage.py runserver` starts without errors
- [ ] `GET /` returns 200 and renders the form (resume textarea, PDF file input, JD textarea, submit button)
- [ ] HTMX and `hx-ext="sse"` are loaded on the page (verifiable in browser devtools)
- [ ] Empty result div is present in the DOM
- [ ] `ANTHROPIC_API_KEY` is loaded from `.env` via `python-dotenv` in `settings.py`

---

## Phase 2: Text-only analysis (batch)

**User stories**: User can paste resume + JD text and receive an ATS analysis

### What to build

Implement `POST /analyze/` as a synchronous view that calls Claude and returns the full response at once. Wire the form to POST to this endpoint using HTMX and swap the raw text response into the result div. No streaming, no PDF, no markdown — but the end-to-end value (resume in → analysis out) is fully demonstrable.

### Acceptance criteria

- [ ] Submitting the form with resume text + JD text calls Claude and displays the raw response in the result div
- [ ] The Claude system prompt enforces the 5-section structure (ATS Score, Keyword Matches, Missing Keywords, Quick Wins, Overall Summary)
- [ ] Empty resume or JD returns a user-visible error (not a 500)
- [ ] `ANTHROPIC_API_KEY` missing or invalid surfaces a clear error message

---

## Phase 3: SSE streaming

**User stories**: User sees the analysis appear word-by-word as Claude generates it

### What to build

Replace the batch view with an SSE endpoint. The form connects via `hx-ext="sse"` and `hx-trigger="sse:message"`, appending chunks to the result div as they arrive. The connection closes cleanly when Claude finishes. The batch Claude call in Phase 2 becomes a streaming call yielding SSE-formatted events.

### Acceptance criteria

- [ ] Analysis text appears incrementally in the result div as Claude streams it
- [ ] SSE connection closes cleanly after the final chunk (no hanging connection)
- [ ] A loading indicator is visible while streaming is in progress
- [ ] Re-submitting the form while a stream is active cancels the previous stream and starts a new one

---

## Phase 4: PDF upload

**User stories**: User can upload a PDF resume instead of pasting text

### What to build

Add `pdfplumber` PDF extraction to `pdf.py`. Update the view to check for an uploaded file first; if present, extract its text and pass it into the existing SSE pipeline. The form already has the file input from Phase 1 — this phase wires it up server-side.

### Acceptance criteria

- [ ] Uploading a valid PDF and submitting produces an analysis based on the PDF's text content
- [ ] If both a PDF and pasted text are provided, the PDF takes priority
- [ ] An invalid or unreadable PDF returns a user-visible error
- [ ] Text-only flow from Phase 3 is unaffected

---

## Phase 5: Markdown rendering

**User stories**: Analysis is displayed as formatted HTML (tables, headers, bold text)

### What to build

After the SSE stream completes, take the accumulated markdown buffer and convert it to HTML using the `markdown` library. Replace the raw text in the result div with the rendered HTML. Tables for Keyword Matches and Missing Keywords sections should render correctly.

### Acceptance criteria

- [ ] Section headers (`##`) render as HTML headings
- [ ] Keyword Matches and Missing Keywords render as proper HTML tables
- [ ] Bold text and inline formatting render correctly
- [ ] Raw markdown is not visible to the user after streaming completes
- [ ] Streaming still shows incremental plain text; only the final render switches to HTML

---

## Phase 6: Polish and styling

**User stories**: The app looks presentable; errors and loading states are handled gracefully

### What to build

Apply CSS to make the UI clean and usable. Add a visible loading/spinner state during streaming. Handle and display edge-case errors (network failure, API timeout). Ensure the form resets cleanly after submission so the user can run another analysis.

### Acceptance criteria

- [ ] Form and result div are readable and well-spaced on a desktop browser
- [ ] A spinner or progress indicator is shown while streaming is active
- [ ] API errors (timeout, rate limit) show a friendly message instead of a broken UI
- [ ] User can submit a new analysis after a previous one completes without refreshing
- [ ] Page is usable on a mobile viewport (basic responsiveness)
