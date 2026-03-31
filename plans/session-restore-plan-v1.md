# Plan: Session State Restoration

> Source PRD: `plans/session-restore-v1.md`

## Architectural decisions

- **No new DB models** — all state is already persisted in `django_session` (SQLite). The fix is purely view + template logic.
- **Routes added**:
  - `POST /compare/reset/` — clears `session["compare"]`, returns intro template
  - `POST /compare/reanalyze/<jd_id>/` — re-triggers SSE stream for a single JD
  - `POST /coach/reset/` — clears `session["coach"]`, returns intro template
- **Session shape is unchanged** — `session["compare"]["jds"]` and `session["coach"]["conversations"]` already store the data needed for restoration; no migration required.
- **Restoration condition**:
  - Compare: `session.get("compare", {}).get("jds")` is non-empty
  - Coach: `session.get("coach", {}).get("experiences")` is non-empty
- **"Start over" becomes a POST** — prevents accidental state loss from browser prefetch or back-button navigation.
- **Collapsed history** — implemented with `<details>`/`<summary>` HTML; no JavaScript.

---

## Phase 1: Compare — Restore Completed Workspace

**User stories**: 1, 2, 4, 11, 12

### What to build

On `GET /compare/`, if the session contains a non-empty `jds` dict, render the workspace view directly instead of the intro screen.

The workspace is rendered server-side with all previously added JDs already in place. JDs with a completed analysis render their full result (score badge, analysis content). JDs without a completed analysis render a placeholder card showing the JD snippet and an empty score cell — the "Re-analyze" interaction is added in Phase 2.

The summary table is pre-populated from session data: each row includes the JD title (from metadata), score badge (if available), and status cell. The `data-score-high` attribute is set on rows that have a score so the existing best-star JS works without any changes.

The stale-resume banner is rendered server-side if `_is_stale()` returns true, exactly as it currently works after a fresh parse.

All tests follow the existing pattern: set up session state directly on the Django test client, make a GET request, assert on response HTML content.

### Acceptance criteria

- [ ] `GET /compare/` with no session (or empty `jds`) renders the intro screen unchanged.
- [ ] `GET /compare/` with one or more completed JDs in session renders the workspace with each analysis visible in the page HTML.
- [ ] The summary table rows are present in the restored HTML with correct score badges.
- [ ] The best-star JS correctly highlights the highest-scoring row on a restored page.
- [ ] The stale-resume banner appears when `resume_version` in the compare session is behind the shared resume's current version.
- [ ] Existing tests (add-jd, stream, metadata) remain green.

---

## Phase 2: Compare — Incomplete JDs and Reset

**User stories**: 3, 5, 6, 13, 14

### What to build

Two additions on top of the restored workspace from Phase 1.

**Incomplete JDs**: Cards for JDs without a completed analysis (interrupted streaming) now show a "Re-analyze" button. Clicking it POSTs to `POST /compare/reanalyze/<jd_id>/`, which re-creates the SSE nonce for that JD and returns a streaming card identical to what the original add-jd flow produces. The summary table row for an incomplete JD shows a "—" score and a pending status until the re-analysis completes.

**Reset**: The "↩ Start over" link in the workspace is replaced with a form that POSTs to `POST /compare/reset/`. That endpoint deletes `session["compare"]` and returns the intro template (or redirects to `GET /compare/`). This prevents browser prefetch or back-navigation from accidentally clearing state.

### Acceptance criteria

- [ ] A restored workspace with an incomplete JD shows a "Re-analyze" button on that card.
- [ ] Clicking "Re-analyze" triggers the SSE stream for that JD and completes normally (score appears, summary row updates).
- [ ] The summary row for an incomplete JD shows "—" and a pending indicator before re-analysis.
- [ ] `POST /compare/reset/` clears `session["compare"]` and the response renders the intro screen.
- [ ] After reset, `GET /compare/` renders the intro screen (not the workspace).
- [ ] Adding a new JD to a restored workspace appends it correctly alongside restored cards.

---

## Phase 3: Coach — Conversation Restoration and Reset

**User stories**: 7, 8, 9, 10, 15

### What to build

On `GET /coach/`, if the session contains parsed `experiences`, render the split-screen view directly instead of the intro screen.

Each experience card in the restored split screen shows a collapsed `<details>`/`<summary>` block if that experience has prior conversation history in `coach["conversations"]`. The summary line shows a count or short label (e.g. "3 messages"). The full message history is inside the `<details>` element and hidden by default. The user can expand it to review previous exchanges.

The message input form for each experience is rendered in its normal state — the user can type and submit a new message immediately, continuing the conversation without any extra steps. The existing SSE stream endpoint is unchanged.

`POST /coach/reset/` clears `session["coach"]` and returns the intro template. The "Start over" link in the split screen is replaced with a POST form pointing to this endpoint.

### Acceptance criteria

- [ ] `GET /coach/` with no session (or no `experiences`) renders the intro screen unchanged.
- [ ] `GET /coach/` with parsed experiences in session renders the split screen directly.
- [ ] An experience with prior conversation history shows a `<details>` block containing the past messages.
- [ ] An experience with no history shows no history block (no empty `<details>` element).
- [ ] The message input form is functional on the restored page; sending a new message streams correctly and appends to the conversation.
- [ ] `POST /coach/reset/` clears `session["coach"]` and the response renders the intro screen.
- [ ] After reset, `GET /coach/` renders the intro screen (not the split screen).
- [ ] Existing coach tests (parse, stream, conversation append) remain green.
