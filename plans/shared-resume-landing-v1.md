# Shared Resume Landing Page v1

A unified resume intake page that replaces the current root landing, stores the resume in session, and pre-fills it across all three tools.

---

## Problem Statement

All three tools require the user to paste or upload their resume individually. A user who wants to try multiple tools must provide their resume multiple times. There is also no cohesive starting experience that orients new users to the three available tools.

## Solution

Replace the root `/` landing page with a resume intake page. Once the user submits their resume, three tool cards appear on the same page letting them choose where to go. The submitted resume is stored in a shared session key and pre-fills each tool's resume field. Users can update their resume at any time; Coach and Compare show a warning banner when the shared resume has changed since their last parse.

---

## User Stories

1. As a new user, I want to land on a page that introduces the three tools, so that I understand what BetterCV offers before committing to one.
2. As a new user, I want to paste or upload my resume once, so that I don't have to re-enter it for each tool.
3. As a user, I want clear feedback that my resume was accepted, so that I feel confident before choosing a tool.
4. As a user, I want to see three tool cards after submitting my resume, so that I can choose which tool to use next.
5. As a user, I want each tool card to show a short description of the tool, so that I can make an informed choice.
6. As a user navigating to the ATS Analyzer, I want both resume and JD fields shown with the resume pre-filled from session, so that I only need to add the job description.
7. As a user navigating to Resume Coach, I want the CV input pre-filled from session, so that I can start coaching without re-uploading.
8. As a user navigating to Multi-JD Compare, I want the resume input pre-filled from session, so that I can immediately start adding job descriptions.
9. As a user who uploaded a PDF on the landing page, I want to see the filename displayed in each tool's resume field, so that I know which file is loaded.
10. As a user, I want a "Change resume" option visible on each tool page, so that I can update my resume mid-session.
11. As a user who updates their resume mid-session, I want Coach and Compare to show a warning banner indicating the resume has changed but not been reprocessed, so that I'm aware existing results may not reflect the latest resume.
12. As a user who re-parses in Coach or Compare after changing the resume, I want the warning banner to disappear, so that I know the tool is using my latest resume.
13. As a user, I want my existing Coach conversations and Compare JD analyses to be preserved when I change my resume, so that I don't lose prior work.
14. As a user who navigates directly to a tool URL without a session resume, I want the tool to still show its own resume upload form as a fallback, so that I can use any tool independently.
15. As a returning user within the same browser session, I want the landing page to reflect that a resume is already loaded, so that I don't have to re-upload it.

---

## Implementation Decisions

### URL Structure Changes
- Root `/` → new home landing page (new `home` app or view in the project's main URL config).
- ATS Analyzer moves from `/` to `/analyzer/` (and sub-paths `/analyzer/analyze/`, `/analyzer/analyze/stream/`).
- Coach and Compare paths remain unchanged (`/coach/`, `/compare/`).

### New Home App / View
- `GET /` renders the resume intake form (paste textarea + PDF upload).
- `POST /resume/` accepts the submission, stores the shared resume in session, and returns the three tool cards as an HTMX fragment that replaces the form — no full page reload.
- If a session resume already exists, `GET /` renders the tool cards directly (skipping the intake form).

### Shared Resume Session Helper
- A small shared helper (e.g. `shared/session.py`) manages `session["shared_resume"]`.
- Stored structure: `{ "resume_text": str, "resume_filename": str | None, "version": int }`.
- The `version` integer increments each time the resume is updated.
- Exposed interface: `get_shared_resume(session)`, `set_shared_resume(session, text, filename)`, `get_resume_version(session)`.
- Tools record the version they last processed; stale detection is a simple integer comparison.

### Stale Resume Warning
- Coach records `session["coach"]["resume_version"]` when `parse()` is called.
- Compare records `session["compare"]["resume_version"]` when `parse_resume()` is called.
- On their index/workspace views, if the session's current `version` exceeds the stored version, a warning banner is rendered.
- The warning clears when the user re-parses (re-submits their tool's resume form), which updates the stored version.
- Existing Coach conversations and Compare JD cards are **not** cleared — only the warning is shown.

### Tool Page Pre-filling
- All three tool index views call `get_shared_resume(session)` and pass resume text and filename to their templates.
- Templates render the textarea pre-populated (or display the filename in place of the upload control) when a session resume is present.
- If no session resume is present, tools render their existing upload form unchanged (fallback, no redirect).

### "Change Resume" Control
- A "Change resume" link appears on all three tool pages when a session resume is loaded.
- Clicking it reveals an inline resume swap form (HTMX-powered) that calls `POST /resume/` to overwrite `session["shared_resume"]`.

---

## Testing Decisions

Good tests verify observable external behavior — HTTP status codes, session state after a request, rendered HTML fragments — not internal implementation details.

### Shared resume session helper
- Unit-tested directly: `set_shared_resume` stores correctly, `get_shared_resume` returns `None` when absent, version increments on each call to `set_shared_resume`.

### Home view
- `GET /` returns 200 with the intake form when no session resume exists.
- `GET /` returns 200 with the tool cards when a session resume is already present.
- `POST /resume/` with valid pasted text stores the shared resume in session and returns the tool cards fragment.
- `POST /resume/` with a valid PDF stores the extracted text and filename in session.
- `POST /resume/` with an empty submission returns an error response.

### Analyzer view (extend existing tests)
- When `session["shared_resume"]` is present, the index page response contains the resume text pre-filled in the resume textarea.
- When absent, the response renders normally without pre-fill.

### Coach view (extend existing tests)
- Stale warning is present in the rendered HTML when `session["shared_resume"]["version"]` exceeds `session["coach"]["resume_version"]`.
- Warning is absent when versions match (after re-parse).

### Compare view (extend existing tests)
- Same stale warning logic as Coach.

Prior art: `analyzer/tests/fakes.py`, `coach/tests/fakes.py`, `compare/tests/fakes.py` — fake services injected via `patch`; session state set directly via `self.client.session` in Django `TestCase`.

---

## Out of Scope

- Persistent resume storage across browser sessions (no database persistence).
- User accounts or authentication.
- Automatically re-running analyses when the resume changes.
- Clearing Coach conversations or Compare JD cards on resume swap.
- A "which tool should I use?" recommendation wizard.

---

## Further Notes

- The `version` integer is simpler than hashing or timestamping and avoids clock/timezone issues.
- The home app should follow the same daisyUI + Tailwind design system used by the existing tools.
- The three tool cards are a natural place to add short marketing copy for each tool — can be iterated on separately.
- The Analyzer currently lives at `/` and is the de-facto landing page; renaming its URL prefix to `/analyzer/` will break any bookmarked links but there are no external links to preserve at this stage.
