# Resume Writer v1

A fourth tool that uses Claude to convert a pasted/uploaded resume into a valid simple-resume YAML file, lets the user edit it in-browser, then invokes the simple-resume Python API to produce a downloadable PDF.

---

## Problem Statement

Users have an existing resume in an unstructured format (PDF, pasted text, Word export). Reformatting it into a clean, structured document is tedious. simple-resume provides a professional, version-control-friendly resume format, but filling out its YAML schema by hand is a barrier to entry.

## Solution

The Resume Writer tool accepts the user's existing resume (from the shared session or entered directly), streams a Claude-generated simple-resume-compatible YAML conversion section by section, displays the result in an editable textarea, and then builds a PDF on demand by calling the simple-resume Python API. The user walks away with a `.yaml` source file and a professionally typeset PDF.

---

## User Stories

1. As a user, I want a Resume Writer card on the landing page, so that I can discover this tool alongside the others.
2. As a user navigating to `/writer/`, I want the resume input pre-filled from my session resume, so that I don't have to re-paste it.
3. As a user without a session resume, I want the tool to show its own resume upload/paste form, so that I can use it independently.
4. As a user, I want Claude to convert my resume to simple-resume YAML, streaming section by section, so that I see progress while the conversion runs.
5. As a user, I want the generated YAML to appear in an editable textarea once streaming is complete, so that I can review and correct any details Claude got wrong.
6. As a user, I want to click a "Build PDF" button after reviewing the YAML, so that I explicitly trigger the build after I'm satisfied.
7. As a user, I want the PDF to be generated server-side and returned as a file download, so that I don't need any local tooling installed.
8. As a user, I want a loading indicator while the PDF is being built, so that I know the process is running.
9. As a user, I want the generated `.yaml` file to also be downloadable, so that I can store and version-control my resume source.
10. As a user, I want errors during YAML generation (e.g. Claude API failure) shown inline, so that I can retry without losing context.
11. As a user, I want errors during PDF build (e.g. invalid YAML, WeasyPrint failure) shown inline below the Build PDF button, so that I know what to fix.

---

## Implementation Decisions

### New `writer` Django App
- URL prefix: `/writer/`
- Routes:
  - `GET /writer/` → index (resume input form, Step 1)
  - `POST /writer/parse/` → accepts resume text, stores nonce, returns SSE container (Step 2)
  - `GET /writer/stream/` → SSE: Claude streams YAML text chunk by chunk
  - `POST /writer/build/` → accepts YAML text, builds PDF via simple-resume Python API, returns file download

### Step-Based UI
- **Step 1:** Resume input form (paste or PDF upload). Pre-filled from `get_shared_resume(session)` if available; shows `resume_filename` as "Loaded from: filename.pdf" when present. Supports PDF upload at parity with the analyzer (pdfplumber extraction, `PdfExtractionError` handling).
- **Step 2:** `POST /writer/parse/` response replaces `#writer-content` with the SSE container + YAML textarea + action buttons. The input form is gone; users refresh the page to start over with a new resume.
- The step transition is an `hx-post` on the form targeting `#writer-content` with `hx-swap="innerHTML"`.

### `WriterService` (`writer/writer_service.py`)
- Constructor takes an `anthropic.Anthropic` client.
- `stream_yaml(resume_text: str)` → yields raw YAML text chunks as Claude generates them.
- Model: `claude-sonnet-4-20250514`, `max_tokens=4000`.
- System prompt instructs Claude to output only valid simple-resume YAML (no prose, no markdown fences). Includes an inline schema reference (~40 lines) covering all field names, the `body:` section structure, and date format (`YYYY` or `YYYY-MM`). Sets `template: resume_no_bars` as the default. The schema is embedded because simple-resume is a small project unlikely to be well-represented in Claude's training data.
- Raises `ClaudeServiceError` on API failures (same pattern as other tools).
- Factory: `get_writer_service()`.

### Streaming and Textarea Accumulation
- Same nonce pattern as Coach and Compare: `POST /writer/parse/` stores `{resume_text}` under `session[nonce]`, returns an HTMX fragment with an SSE container pointing to `/writer/stream/?key={nonce}`.
- SSE stream emits `chunk` events with raw YAML text. The frontend accumulates them into the textarea via a `htmx:sseMessage` JS listener (not `sse-swap` — `<textarea>` value is a property, not innerHTML):
  ```javascript
  document.addEventListener('htmx:sseMessage', (e) => {
    if (e.detail.type === 'chunk')
      document.getElementById('yaml-output').value += e.detail.data;
  });
  ```
- A `done` SSE event enables the "Build PDF" button and "Download YAML" button via the same listener checking `e.detail.type === 'done'`.

### `SimpleResumeBuilder` (`writer/simple_resume_builder.py`)
- `build_pdf(yaml_content: str, session_key: str) -> bytes` — writes YAML to `/tmp/resume_<session_key>.yaml`, calls the simple-resume Python API (`from simple_resume import generate; from simple_resume.core.models import GenerationConfig`), reads the output PDF, cleans up temp files.
- Session key is used in filenames to avoid collisions from concurrent requests.
- **Output path is a spike** (Phase 1): confirm where `generate()` writes the PDF relative to the input file before finalising cleanup logic.
- Uses `GenerationConfig(formats=["pdf"])`.
- Raises `SimpleResumeBuildError(message)` on `ValidationError`, `GenerationError`, or any other `SimpleResumeError` subclass, or if the output PDF is not produced.

### Build Endpoint
- `POST /writer/build/` receives the (possibly edited) YAML and the session key as form data.
- Uses `hx-post` with `hx-swap="none"` — HTMX does not swap the response.
- A JS `htmx:configRequest` listener sets `xhr.responseType = "arraybuffer"` before the request fires.
- A JS `htmx:afterRequest` listener handles both outcomes:
  - Status 200: create a `Blob` from `xhr.response`, generate an object URL, trigger a download link click with `filename="resume.pdf"`.
  - Status 422: inject `xhr.responseText` into `#build-error` (a div directly below the "Build PDF" button, initially empty).
- On `SimpleResumeBuildError`, returns a 422 response with an HTMX-rendered error fragment.

### Download YAML
- Client-side only: a JS click handler on the "Download YAML" button creates a `Blob` from `textarea.value` and triggers a download with `filename="resume.yaml"`. No server round-trip.

### Shared PDF Extraction
- `analyzer/pdf.py` moves to `shared/pdf.py`. `analyzer` updates its import to `from shared.pdf import extract_text, PdfExtractionError`. Tests move to `shared/tests/`. No backward-compat shim.
- The writer imports from `shared.pdf` directly.

### Python Dependency
- Add `simple-resume` (pinned to `0.3.2`) to the project via `uv add simple-resume`.
- PDF generation uses WeasyPrint (a `simple-resume` core dependency). No LaTeX or Node.js required.
- WeasyPrint requires system libraries (Cairo, Pango, GDK-PixBuf). These are added to the Dockerfile as an `apt-get install` layer before `uv sync`.
- Available templates: `resume_no_bars`, `resume_with_bars`, `resume_modern`, `resume_professional`, `resume_creative`. Default is `resume_no_bars`; users can change it by editing the YAML.

---

## Testing Decisions

Tests are written TDD (red-green) at every phase. Good tests verify observable behavior: HTTP responses, file output, error messages — not internal API mechanics.

### `WriterService`
- Tested by passing a `MagicMock(spec=anthropic.Anthropic)` to its constructor (same pattern as `ClaudeService`).
- Verify that `stream_yaml()` yields chunks and that `ClaudeServiceError` is raised on API failure.

### `SimpleResumeBuilder`
- Tested by patching `simple_resume.generate`.
- Verify that valid YAML produces a `bytes` return value and that a `ValidationError` / `GenerationError` raises `SimpleResumeBuildError`.
- A `FakeSimpleResumeBuilder` (returns stub PDF bytes) is used in view tests.

### Writer views
- `GET /writer/` with session resume: response contains pre-filled resume text and filename.
- `GET /writer/` without session resume: response contains the empty upload form.
- `POST /writer/parse/` with pasted resume text: session stores nonce, response contains SSE container.
- `POST /writer/parse/` with PDF upload: pdfplumber extraction runs, session stores nonce.
- `POST /writer/parse/` with empty text: returns error response.
- `POST /writer/build/` with valid YAML (using `FakeSimpleResumeBuilder`): returns `application/pdf` response.
- `POST /writer/build/` when `SimpleResumeBuildError` is raised: returns 422 with error fragment.

Prior art: `analyzer/tests/fakes.py`, `coach/tests/fakes.py` — inject fakes via `patch("writer.views.get_writer_service", ...)`.

---

## Implementation Phases

### Phase 1 — Spike
- Install `simple-resume==0.3.2` via `uv add`.
- Write a throwaway script: write a minimal `resume.yaml` to `/tmp/`, call `generate()` with `GenerationConfig(formats=["pdf"])`, confirm where the output PDF is written, document cleanup strategy.
- Add WeasyPrint system libs to Dockerfile (`apt-get install libcairo2 libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 shared-mime-info`).

### Phase 2 — Shared PDF extraction
- Move `analyzer/pdf.py` → `shared/pdf.py`.
- Update `analyzer` imports.
- Move PDF extraction tests to `shared/tests/`.

### Phase 3 — Writer app skeleton
- Django app registration, URLs, index view.
- Step 1: resume input form with paste + PDF upload, session pre-fill, filename display.

### Phase 4 — Streaming
- `WriterService` with system prompt embedding simple-resume schema.
- `POST /writer/parse/` nonce pattern.
- `GET /writer/stream/` SSE.
- Step 2 fragment: SSE container, textarea, disabled action buttons.
- JS listeners for chunk accumulation and `done` button activation.
- Download YAML client-side button.

### Phase 5 — Build
- `SimpleResumeBuilder` using output path confirmed in Phase 1 spike.
- `POST /writer/build/` endpoint.
- JS `htmx:configRequest` + `htmx:afterRequest` for blob download and error injection.
- `#build-error` div and 422 error fragment.

### Phase 6 — Polish
- Landing page card.
- Dockerfile WeasyPrint layer verification in CI/local Docker build.
- README documentation for WeasyPrint system deps.

---

## Out of Scope

- HTML or LaTeX output formats (PDF only for v1).
- In-browser YAML schema validation or autocomplete.
- Saving generated YAML to a database.
- User-selectable templates via UI (user edits the `template:` field in YAML directly).
- Color palette selection UI.
- A YAML diff view comparing the original resume to the generated one.
- Stale resume detection (unlike Coach and Compare, the writer has no persisted state that can go stale).

---

## Further Notes

- The simple-resume YAML schema is validated by the Python API during build; the Claude system prompt embeds the schema to minimise hallucinated field names and build failures.
- `simple_resume` exceptions all inherit from `SimpleResumeError` — catch the base class in `SimpleResumeBuilder` for a clean error surface.
- Pin `simple-resume==0.3.2` to avoid unexpected schema changes breaking the Claude prompt.
- WeasyPrint is Python-native; no LaTeX or Node.js required anywhere in this feature.
