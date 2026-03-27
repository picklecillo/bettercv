# PRD: Resume Coach

## Problem Statement

Job seekers often write CV work experience sections that describe their job title and responsibilities rather than what they actually accomplished. Generic, role-focused descriptions score poorly with ATS systems and fail to stand out to human reviewers. Users need help translating what they actually did on the job into compelling, achievement-focused descriptions — but they often don't know where to start or how to phrase it.

## Solution

A Resume Coach flow that lets users load their CV, select a work experience entry, and have a guided multi-turn conversation with an AI coach. The coach asks questions to draw out specifics about what the user actually did and achieved, then proposes a rewritten paragraph-form description. The user can push back, redirect, and refine until they're happy, then copy the result.

## User Stories

1. As a job seeker, I want to upload my CV as a PDF or paste it as text, so that I can start a coaching session without manual re-entry.
2. As a job seeker, I want the app to automatically identify my work experience entries, so that I don't have to manually parse my own CV.
3. As a job seeker, I want to see a clear error message if my CV could not be parsed, so that I understand what went wrong and can try again.
4. As a job seeker, I want to see my original CV text alongside the coaching chat, so that I can refer back to what I originally wrote.
5. As a job seeker, I want to select a specific work experience to coach, so that I can focus on one job at a time.
6. As a job seeker, I want the AI to start the conversation with a question, so that I'm guided rather than having to know what to say first.
7. As a job seeker, I want the AI to ask me questions about what I actually did and achieved in the role, so that the rewrite reflects my real contributions rather than generic responsibilities.
8. As a job seeker, I want to receive a paragraph-form rewritten description, so that I get a ready-to-use output by default.
9. As a job seeker, I want to push back on the AI's proposed description ("make it shorter", "focus more on X"), so that the final result reflects my preferences.
10. As a job seeker, I want the AI's replies to stream in word by word, so that I get immediate feedback rather than waiting for a full response.
11. As a job seeker, I want to copy the AI's proposed description to my clipboard, so that I can paste it into my CV.
12. As a job seeker, I want to start a fresh coaching session for a different work experience entry, so that I can improve multiple jobs in a single visit.
13. As a job seeker, I want the Resume Coach to be a separate flow from the ATS Analyzer, so that the two tools don't interfere with each other.

## Implementation Decisions

### Modules

**`CoachService`** — new service class (analogous to `ClaudeService`) responsible for two operations:
- `parse_cv(cv_text) → list[WorkExperience]`: sends the CV to Claude with a structured extraction prompt; returns a list of work experience objects (company, title, dates, original description). Raises a `CoachParseError` if Claude cannot identify work experiences.
- `stream_reply(work_experience, history) → Iterator[str]`: streams the next coach reply given a work experience and the full conversation history so far.

`CoachService` takes an injected Anthropic client via `__init__`, matching the pattern of `ClaudeService`. A `get_coach_service()` factory handles production wiring.

**`WorkExperience`** — a dataclass or TypedDict: `{company, title, dates, original_description}`. Returned by `parse_cv`, stored in session, passed to `stream_reply`.

**Views** — three new views added to `analyzer/views.py`:
- `GET /coach/` — renders the coach entry page (CV input form)
- `POST /coach/parse/` — extracts CV text (PDF or paste), calls `CoachService.parse_cv()`, stores parsed experiences + raw CV text in session, returns HTML list of work experience entries
- `GET /coach/stream/?key=<key>` — SSE endpoint; reads conversation context from session, calls `CoachService.stream_reply()`, yields SSE events (`chunk`, `done`). The key identifies the session slot for this job's conversation.

**Session schema** (per coach session):
```
session["coach"] = {
  "cv_text": str,
  "experiences": list[WorkExperience],
  "conversations": {
    "<experience_index>": list[{"role": str, "content": str}]
  }
}
```

**Template** — `/coach/index.html`: two-phase layout.
- Phase 1: CV input form (paste + PDF upload, same pattern as `analyzer/index.html`).
- Phase 2 (after parsing): split-screen — left panel shows original CV text, right panel shows selected work experience and chat interface. HTMX handles transitions between phases and chat message submission.

### Streaming and conversation flow

- The coach always sends the first message (no user input required to start).
- After the user selects a work experience, a POST initiates the first turn (empty user message or a fixed prompt); the SSE stream returns Claude's opening question.
- Subsequent turns: user types a message → HTMX POSTs it → stored in session history → SSE stream returns next reply.
- Each SSE response appends to the conversation history in the session before streaming begins.

### Prompt design

- **Parse prompt**: instructs Claude to return a JSON array of work experiences. The view validates the JSON before storing in session; if invalid or empty, raises `CoachParseError`.
- **Coach system prompt**: establishes the coach persona, instructs Claude to ask questions that surface achievements and impact, default output as a paragraph, and to incorporate user feedback in subsequent turns.
- **Coach user prompt**: passes the original work experience description and the full conversation history.

### Error handling

- `CoachParseError` (new exception, analogous to `PdfExtractionError`) — raised when CV parsing fails. Surface as a styled error div in the parse response.
- Streaming errors follow the same pattern as V1: errors are sent as a chunk event with a `.result-error` div, followed by `done`.

## Testing Decisions

- Tests follow the existing pattern: inject a `FakeCoachService` (analogous to `FakeClaudeService`) into view tests; test `CoachService` directly with a `MagicMock(spec=anthropic.Anthropic)`.
- Test `parse_cv` for: valid CV with multiple experiences, CV with no detectable experiences (raises `CoachParseError`), malformed JSON response from Claude (raises `CoachParseError`).
- Test `stream_reply` for: correct conversation history is passed to the API, chunks are yielded correctly.
- Test views for: parse error surface, successful parse returns experience list, SSE stream sends chunks and done event, conversation history accumulates across turns.
- Do not test Claude prompt wording — test the behaviour at module boundaries only.
- Tests go in `analyzer/tests/test_coach.py` (service) and extend `analyzer/tests/test_views.py` (views).

## Out of Scope

- Persisting coaching sessions across page refreshes or browser sessions.
- Assembling a full rewritten CV from all coached experiences.
- Exporting the coaching output as a document.
- Connecting the Resume Coach output back to the ATS Analyzer flow.
- User accounts or any form of authentication.
- Bullet-point output format (paragraph is the default; the user can request bullets via conversation).

## Further Notes

- The Resume Coach shares the Anthropic client infrastructure with the ATS Analyzer. `CoachService` and `ClaudeService` are sibling classes, not a hierarchy — they serve different purposes and have different prompt structures.
- The `/coach/` URL namespace is separate from `/analyze/`; no existing routes are modified.
- The session schema for the coach (`session["coach"]`) is separate from the ATS analyzer's session keys (UUID-keyed slots) to avoid collisions.
