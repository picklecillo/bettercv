# Plan: Resume Coach

> Source PRD: docs/resume_coach_prd.md

## Architectural decisions

### App structure
- **New `coach` Django app** — `coach/views.py`, `coach/coach_service.py`, `coach/templates/coach/`, `coach/tests/`. Fully separate from `analyzer`.
- **Shared utilities** — `analyzer/pdf.py` stays in `analyzer`; coach views import it directly (`from analyzer.pdf import extract_text_from_pdf`).
- **Navigation** — Both tools share the same header design. The header is updated to include nav links to `/` (ATS Analyzer) and `/coach/` (Resume Coach).

### Routes
- `GET /coach/` — CV input form
- `POST /coach/parse/` — extract + parse CV, return experience list HTML; full `<main>` swap (`hx-target="main" hx-swap="innerHTML"`) transitions to split-screen
- `POST /coach/chat/` — store user message nonce in session, return user bubble + SSE container fragment (`beforeend` swap into chat transcript)
- `GET /coach/stream/?key=<nonce>` — pop nonce, stream Claude reply, commit exchange to history after stream completes
- `GET /coach/conversation/<exp_index>/` — return chat history HTML fragment for switching between experiences

### Session schema
```
session["coach"] = {
  "cv_text": str,
  "experiences": list[WorkExperience],
  "conversations": {
    "<exp_index>": list[{"role": str, "content": str}]
  }
}
```
The `session["coach"]` key is separate from the UUID-keyed ATS analyzer slots.

### Key models
`WorkExperience` — `{ company: str, title: str, dates: str, original_description: str }`
`dates` is a plain string (e.g. `"Jan 2019 – Mar 2022"`), not structured — CV date formats are too inconsistent to normalise.

### Service layer
`CoachService` with two methods:
- `parse_cv(cv_text) → list[WorkExperience]` — uses Claude **tool use** (`tool_choice={"type": "tool", "name": "extract_work_experiences"}`) to force a structured JSON response. Raises `CoachParseError` if the tool use block is missing or the array is empty.
- `stream_reply(work_experience: WorkExperience, history: list[dict]) → Iterator[str]` — streams the next coach reply. Receives the full `WorkExperience` object (company, title, dates, original description all available for context). `max_tokens=2000`.

Takes an injected `anthropic.Anthropic` client via `__init__`. Production code calls `get_coach_service()`.

### Exceptions
`CoachParseError` — raised when CV parsing fails (missing tool use block, empty experience array). Surfaced as a styled error div.

### Streaming and conversation flow
- **Nonce pattern** — `POST /coach/chat/` generates a UUID nonce and stores `{exp_index, user_message}` under `session[nonce]`. Returns an HTML fragment: the user message bubble (rendered immediately) followed by an SSE container pointing to `/coach/stream/?key=<nonce>`.
- `GET /coach/stream/` pops the nonce, calls `CoachService.stream_reply()`, streams chunks, then **commits the full exchange to session history after the stream completes** (not before). Partial/errored streams are never written to history.
- On stream error: emit an inline error bubble in the chat, re-enable the chat input pre-filled with the failed message so the user can retry.

### First-turn bootstrapping
When the user selects a work experience, HTMX POSTs a **hidden prefilled message** (the `original_description`) to `/coach/chat/`. This message is not shown as a user bubble — the chat opens directly with Claude's first coaching question. The prefilled message is stored in history as a `user` role turn so Claude has the full context.

### Switching between experience conversations
- Clicking an experience in the right-panel list calls `GET /coach/conversation/<exp_index>/`.
- If a conversation exists for that index: returns the chat history HTML + input area (swaps only the chat area below the experience list).
- If no conversation exists yet: triggers the first-turn POST flow.
- The experience list stays persistently visible in the right panel throughout.

---

## Phase 1: CV Input and Parsing

**User stories**: 1, 2, 3, 13

### What to build

`GET /coach/` renders a coach entry page with a CV input form (paste textarea + PDF file upload, same pattern as the ATS Analyzer). `POST /coach/parse/` extracts text from the submission (PDF takes priority over paste), calls `CoachService.parse_cv()`, stores the raw CV text and the parsed work experience list in `session["coach"]`, and returns the full split-screen HTML (targeting `<main>`). If parsing fails — unreadable PDF, no experiences detected, malformed tool use response — a styled error div is returned instead.

`CoachService.parse_cv()` uses Claude tool use with a forced `extract_work_experiences` tool call. Returns a `list[WorkExperience]`. Raises `CoachParseError` on missing tool use block or empty array.

### Acceptance criteria

- [x] `GET /coach/` returns 200 with a CV input form (paste textarea + PDF upload)
- [x] `POST /coach/parse/` with pasted text swaps `<main>` to split-screen with an experience list
- [x] `POST /coach/parse/` with a PDF file extracts text and returns the same
- [x] PDF upload takes priority over pasted text when both are submitted
- [x] Submitting neither returns an error div
- [x] An unreadable PDF surfaces a `PdfExtractionError` as an error div
- [x] A CV with no detectable work experiences surfaces a `CoachParseError` error div
- [x] Parsed experiences and raw CV text are stored in `session["coach"]`
- [x] `CoachService.parse_cv()` is tested directly: valid CV (tool use response), no experiences, missing tool use block
- [x] `coach` app routes are registered under `/coach/` and do not touch `/analyze/` routes
- [x] Header includes nav links to both tools

---

## Phase 2: Work Experience Selection and First AI Message

**User stories**: 4, 5, 6, 7, 10

### What to build

The split-screen layout shows CV text in the left panel and the experience list + chat area in the right panel. When the user selects a work experience, HTMX POSTs to `/coach/chat/` with the experience index and the `original_description` as a hidden prefilled message. The view stores a nonce in session and returns a fragment with an SSE container (no user bubble for the prefilled message). `GET /coach/stream/?key=<nonce>` pops the nonce, calls `CoachService.stream_reply()` with the full `WorkExperience` and empty prior history, streams Claude's opening question word by word, and commits the exchange to session history on completion.

### Acceptance criteria

- [x] After a successful parse, `<main>` shows the split-screen layout (CV text left, experience list + chat right)
- [x] Selecting a work experience starts a coaching conversation automatically (no manual prompt from the user)
- [x] The chat area opens with Claude's first question — no user bubble for the prefilled message
- [x] Claude's opening question streams in word by word via SSE
- [x] The user message + assistant reply are committed to `session["coach"]["conversations"][<exp_index>]` only after the stream completes
- [x] A stream error shows an inline error bubble and re-enables the chat input pre-filled with the failed message
- [x] `CoachService.stream_reply()` is tested: full `WorkExperience` object passed to API, chunks yielded correctly
- [x] View tests: selecting an experience returns a nonce-keyed SSE container; stream pops nonce and emits chunk + done events

---

## Phase 3: Multi-turn Conversation

**User stories**: 8, 9, 10

### What to build

A chat input and send button appear below the streaming area in the right panel. When the user submits a message, HTMX POSTs to `/coach/chat/` with the experience index and the user's message text. The view generates a nonce, stores `{exp_index, user_message}` in session, and returns a fragment: the user message bubble followed by a new SSE container. `GET /coach/stream/` pops the nonce, calls `CoachService.stream_reply()` with the full conversation history, streams Claude's reply, and commits the exchange to history on completion.

Switching between experience conversations is handled by `GET /coach/conversation/<exp_index>/`, which returns the existing chat history HTML + input area, swapping only the chat panel below the experience list.

### Acceptance criteria

- [x] User can submit a message via the chat input
- [x] The user message bubble appears immediately (returned in the POST response fragment)
- [x] Claude's reply streams in word by word below the user bubble
- [x] Conversation history accumulates correctly across multiple turns
- [x] The full history (all prior turns) is passed to `CoachService.stream_reply()` on each turn
- [x] `GET /coach/conversation/<exp_index>/` returns history HTML for an already-coached experience
- [x] `GET /coach/conversation/<exp_index>/` triggers the first-turn flow for an uncoached experience
- [x] Switching experiences does not affect other experiences' histories
- [x] View tests: history accumulates across multiple POST → stream cycles; conversation switching works

---

## Phase 4: Copy and Reset

**User stories**: 11, 12

### What to build

A "Copy" button appears on each AI message bubble. Clicking it copies the message text to the clipboard via `navigator.clipboard.writeText`. A "Start over" link in the header (or a button on the page) navigates to `GET /coach/` — a full page reload that clears the coach session and returns to the CV input form.

### Acceptance criteria

- [x] Each AI message bubble has a "Copy" button that copies its text to the clipboard
- [x] "Start over" navigates to `GET /coach/` (full reload; no HTMX)
- [x] Starting a fresh session clears `session["coach"]`
- [x] The copy button is keyboard-accessible
- [x] Switching to a different experience via the list does not affect any other experience's history
