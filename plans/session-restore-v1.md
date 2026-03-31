# PRD: Session State Restoration for JD Compare and Resume Coach

## Problem Statement

When a user reloads the page (or navigates away and returns within the same browser session), both the JD Compare workspace and the Resume Coach conversation are lost. The user is dropped back to the intro screen and must start over — re-adding all job descriptions, re-triggering analyses, and re-entering coaching conversations.

This is frustrating because the underlying state (parsed JDs, completed analyses, parsed experiences, conversation history) is already stored in Django's session, backed by SQLite. The data exists; the views just don't use it on a fresh page load.

## Solution

On a fresh GET to `/compare/` or `/coach/`, each view checks whether the session contains existing tool state and, if so, renders the workspace/conversation view directly instead of the intro screen. No new database models are needed — the fix is purely view and template logic reading from the existing session.

For JD Compare:
- The workspace is restored with all previously added JDs.
- JDs with a completed analysis are rendered server-side with their full result.
- JDs whose analysis was interrupted (streaming in progress when the user left) are rendered with a "Re-analyze" button so the user can manually re-trigger the SSE stream.
- The summary table is pre-populated from session data.

For Resume Coach:
- The split-screen view is restored with all parsed experiences.
- Each experience shows a collapsed conversation history (past messages visible but not dominant).
- The user can expand any experience and continue coaching from where they left off.

A "Start over" action clears the tool's session state and returns the user to the intro screen.

## User Stories

1. As a job seeker, I want the JD Compare workspace to reappear when I reload the page, so that I don't lose the job descriptions I've already added and analyzed.
2. As a job seeker, I want completed ATS analyses to be visible immediately after a reload, so that I don't have to wait for Claude to re-analyze each job description.
3. As a job seeker, I want JDs whose analysis was interrupted to show a "Re-analyze" button after a reload, so that I can selectively re-run only the incomplete ones.
4. As a job seeker, I want the summary score table to be pre-populated with all previously analyzed JDs after a reload, so that I can immediately compare scores without re-running anything.
5. As a job seeker, I want to be able to add new JDs on top of my restored workspace, so that I can continue building my comparison after a reload.
6. As a job seeker, I want a "Start over" action in the Compare workspace that clears all session state, so that I can begin a fresh comparison when I'm done with the current one.
7. As a job seeker, I want the Resume Coach split-screen view to reappear when I reload, so that I don't lose my parsed CV and coaching conversations.
8. As a job seeker, I want my past coaching messages for each experience to be visible (collapsed) after a reload, so that I can review what was discussed and continue from there.
9. As a job seeker, I want to be able to send a new coaching message to any experience immediately after a reload, so that the conversation is seamlessly resumable.
10. As a job seeker, I want a "Start over" action in the Coach view that clears session state, so that I can start a new coaching session with a different CV.
11. As a job seeker, I want the stale-resume banner to still appear after a reload if my shared resume has changed since I last ran the tool, so that I'm prompted to re-parse.
12. As a job seeker, I want the restored state to reflect the correct resume version, so that staleness detection continues to work correctly after a reload.
13. As a job seeker, I want the "Re-analyze" button for an incomplete JD to trigger the same SSE stream as the original analysis, so that the experience is consistent.
14. As a job seeker, I want the summary table row for an incomplete JD to show a pending state after a reload, so that I can clearly tell which scores are still missing.
15. As a job seeker, I want the restored Coach view to show which experiences have prior conversation history, so that I know where I left off.

## Implementation Decisions

### Compare — view changes
- The `index` view (`GET /compare/`) checks `request.session.get("compare")`. If it contains a non-empty `jds` dict, it renders the workspace template directly instead of the intro template. No redirect needed.
- A new `reset` endpoint (`POST /compare/reset/`) clears `request.session["compare"]` and returns the intro template. The "Start over" link in the workspace is updated to POST to this endpoint instead of being a plain GET link.

### Compare — workspace template changes
- A new server-rendered section iterates over `compare["jds"]` and renders each JD card on page load.
- Completed JDs (`analysis` is non-null) render their full analysis using the existing `.analysis-result` / `.analysis-card` markup, server-side.
- Incomplete JDs (`analysis` is null) render a card with a "Re-analyze" button and a pending score placeholder in the summary table.
- The "Re-analyze" button triggers the existing SSE stream for that specific JD (new endpoint `POST /compare/reanalyze/<jd_id>/` or reuse of the add-jd flow).
- The existing `<div id="jd-cards">` and `<tbody id="summary-tbody">` remain as append targets for newly added JDs.

### Compare — summary table restoration
- Each restored summary row is rendered server-side with the score badge (if available) or a "—" placeholder and "Re-analyze" link.
- Server-rendered rows include `data-score-high` attributes so the existing best-star JS works without changes.

### Coach — view changes
- The `index` view (`GET /coach/`) checks `request.session.get("coach")`. If it contains `experiences`, it renders `split_screen.html` with the existing session state as context.
- A new `reset` endpoint (`POST /coach/reset/`) clears `request.session["coach"]` and returns the intro template.

### Coach — split screen template changes
- Each experience card receives its `history` list (messages from `coach["conversations"]`).
- If `history` is non-empty, a collapsed history section is shown beneath the experience header, implemented with `<details>`/`<summary>` — no JS required.
- The existing message-input form and SSE stream endpoint are unchanged; conversation continues normally after restoration.

### No new DB models
- All restored state comes from `request.session["compare"]` and `request.session["coach"]`, already persisted in the `django_session` SQLite table.
- Session state survives page reloads within the same browser session (cookie valid, server running).

### Staleness handling
- Staleness detection (`_is_stale()` comparing `resume_version`) is unchanged. The stale banner is rendered server-side in the restored workspace when applicable.

## Testing Decisions

Good tests assert on observable HTTP response behavior (response content, session state after the request) rather than internal call paths.

**Compare view — restoration tests:**
- `GET /compare/` with no session returns the intro template.
- `GET /compare/` with completed JDs in session returns the workspace with analysis HTML present.
- `GET /compare/` with incomplete JDs returns the workspace with "Re-analyze" buttons.
- `GET /compare/` with a stale resume version renders the stale-resume banner.
- `POST /compare/reset/` clears `session["compare"]` and returns the intro.

**Coach view — restoration tests:**
- `GET /coach/` with no session returns the intro template.
- `GET /coach/` with parsed experiences in session returns the split screen.
- `GET /coach/` with conversation history returns the split screen with history markup (`<details>`) present.
- `POST /coach/reset/` clears `session["coach"]` and returns the intro.

**Prior art:** `apps/compare/tests/test_views.py` and `apps/coach/tests/test_views.py` use `FakeCompareService` / `FakeCoachService` injected via `patch`. New tests follow the same pattern: set up session state directly on the test client's session, make the request, assert on response content.

## Out of Scope

- Cross-device persistence or survival after browser close (would require user accounts or shareable URL tokens).
- Automatic re-streaming of incomplete JD analyses on reload (user must click "Re-analyze").
- Persisting in-progress SSE streams across reloads (streams are inherently transient).
- State restoration for the ATS Analyzer or Resume Writer tools.
- Any changes to the shared resume panel or session structure.

## Further Notes

- The fix is purely additive: existing session data is already in the right shape; no session schema migration needed.
- "Start over" should use a POST endpoint to avoid accidental state loss from browser prefetch or back-button navigation.
- The collapsed history toggle in the Coach uses `<details>`/`<summary>` — no JavaScript needed.
- Session expiry (Django default: 2 weeks) naturally bounds the lifetime of restored state; no explicit TTL management needed.
