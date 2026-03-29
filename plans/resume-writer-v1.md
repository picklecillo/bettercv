# Resume Writer v1

A fourth tool that uses Claude to convert a pasted/uploaded resume into a valid yamlresume YAML file, lets the user edit it in-browser, then invokes the yamlresume CLI to produce a downloadable PDF.

---

## Problem Statement

Users have an existing resume in an unstructured format (PDF, pasted text, Word export). Reformatting it into a clean, structured document is tedious. yamlresume provides a professional, version-control-friendly resume format, but filling out its YAML schema by hand is a barrier to entry.

## Solution

The Resume Writer tool accepts the user's existing resume (from the shared session or entered directly), streams a Claude-generated yamlresume-compatible YAML conversion section by section, displays the result in an editable textarea, and then builds a PDF on demand by invoking the yamlresume CLI as a subprocess. The user walks away with a `.yaml` source file and a professionally typeset PDF.

---

## User Stories

1. As a user, I want a Resume Writer card on the landing page, so that I can discover this tool alongside the others.
2. As a user navigating to `/writer/`, I want the resume input pre-filled from my session resume, so that I don't have to re-paste it.
3. As a user without a session resume, I want the tool to show its own resume upload/paste form, so that I can use it independently.
4. As a user, I want Claude to convert my resume to yamlresume YAML, streaming section by section, so that I see progress while the conversion runs.
5. As a user, I want the generated YAML to appear in an editable textarea once streaming is complete, so that I can review and correct any details Claude got wrong.
6. As a user, I want to click a "Build PDF" button after reviewing the YAML, so that I explicitly trigger the build after I'm satisfied.
7. As a user, I want the PDF to be generated server-side and returned as a file download, so that I don't need any local tooling installed.
8. As a user, I want a loading indicator while the PDF is being built, so that I know the process is running.
9. As a user, I want the generated `.yaml` file to also be downloadable, so that I can store and version-control my resume source.
10. As a user, I want errors during YAML generation (e.g. Claude API failure) shown inline, so that I can retry without losing context.
11. As a user, I want errors during PDF build (e.g. invalid YAML, missing LaTeX) shown inline with a clear message, so that I know what to fix.
12. As a user, I want to regenerate the YAML from scratch, so that I can try again if the conversion missed sections.

---

## Implementation Decisions

### New `writer` Django App
- URL prefix: `/writer/`
- Routes:
  - `GET /writer/` → index (resume input + conversion UI)
  - `POST /writer/parse/` → accepts resume text, stores nonce, returns SSE container
  - `GET /writer/stream/` → SSE: Claude streams YAML text chunk by chunk
  - `POST /writer/build/` → accepts YAML text, builds PDF via yamlresume CLI, returns file download

### `WriterService` (`writer/writer_service.py`)
- Constructor takes an `anthropic.Anthropic` client.
- `stream_yaml(resume_text: str)` → yields SSE text chunks as Claude generates the YAML.
- System prompt instructs Claude to output only valid yamlresume YAML (no prose, no markdown fences), populating as many schema fields as it can infer from the source resume.
- Raises `ClaudeServiceError` on API failures (same pattern as other tools).

### `YamlResumeBuilder` (`writer/yamlresume_builder.py`)
- `build_pdf(yaml_content: str) -> bytes` — writes YAML to a temp file, invokes `npx yamlresume build <file> --no-pdf=false` (or equivalent) as a subprocess, reads the output PDF, cleans up temp files.
- Raises `YamlResumeBuildError(message)` if the CLI exits non-zero or PDF is not produced.
- The yamlresume CLI is available via `npx` (no global install required); a `package.json` at the project root pins the version.

### Streaming Pattern
- Same nonce pattern as Coach and Compare: `POST /writer/parse/` stores `{resume_text}` under `session[nonce]`, returns an HTMX fragment with an SSE container pointing to `/writer/stream/?key={nonce}`.
- The SSE stream emits `data:` events with raw YAML text chunks. The frontend accumulates them into the textarea value.
- A `done` event signals streaming completion and enables the "Build PDF" button and the "Download YAML" link.

### Build Endpoint
- `POST /writer/build/` receives the (possibly edited) YAML as form data.
- Invokes `YamlResumeBuilder.build_pdf()`.
- Returns the PDF as `application/pdf` with `Content-Disposition: attachment; filename="resume.pdf"`.
- On `YamlResumeBuildError`, returns a 422 response with an HTMX-rendered error fragment.

### Session Integration
- Index view calls `get_shared_resume(session)` to pre-fill the resume textarea.
- No writer-specific session key is needed — the nonce covers the stream, and the build receives YAML directly from the form.

### Node.js Dependency
- A `package.json` at the project root (or in a `writer/` subdirectory) lists `yamlresume` as a dev/runtime dependency.
- The Django subprocess call uses `npx yamlresume` so no global install is required.
- `yamlresume doctor` can be used in a management command or startup check to verify LaTeX dependencies are present.
- LaTeX (XeTeX or Tectonic) must be installed on the server for PDF generation; this is documented in the project README.

---

## Testing Decisions

Good tests verify observable behavior: HTTP responses, file output, error messages — not internal subprocess mechanics.

### `WriterService`
- Tested by passing a `MagicMock(spec=anthropic.Anthropic)` to its constructor (same pattern as `ClaudeService`).
- Verify that `stream_yaml()` yields chunks and that `ClaudeServiceError` is raised on API failure.

### `YamlResumeBuilder`
- Tested by patching `subprocess.run` (or a thin wrapper around it).
- Verify that valid YAML produces a `bytes` return value and that a non-zero exit code raises `YamlResumeBuildError`.
- A `FakeYamlResumeBuilder` (returns stub PDF bytes) is used in view tests.

### Writer views
- `GET /writer/` with session resume: response contains pre-filled resume text.
- `GET /writer/` without session resume: response contains the empty upload form.
- `POST /writer/parse/` with valid resume text: session stores nonce, response contains SSE container.
- `POST /writer/parse/` with empty text: returns error response.
- `POST /writer/build/` with valid YAML (using `FakeYamlResumeBuilder`): returns `application/pdf` response.
- `POST /writer/build/` when `YamlResumeBuildError` is raised: returns 422 with error fragment.

Prior art: `analyzer/tests/fakes.py`, `coach/tests/fakes.py` — inject fakes via `patch("writer.views.get_service", ...)`.

---

## Out of Scope

- HTML, Markdown, or LaTeX output formats (PDF only for v1).
- In-browser YAML schema validation or autocomplete.
- Saving generated YAML to a database.
- Multiple resume templates (v1 uses the yamlresume default).
- A YAML diff view comparing the original resume to the generated one.

---

## Further Notes

- The yamlresume YAML schema is validated by the CLI during build; Claude should be prompted to adhere strictly to the schema to minimise build failures.
- PDF generation requires a LaTeX engine on the server — this is a significant system dependency not present in the current stack. Consider documenting a Docker-based dev setup or using yamlresume's HTML output as a fallback during development.
- yamlresume is a Node.js CLI (`npx yamlresume`), not a Python library. All interaction goes through `subprocess`.
- The `package.json` should pin a specific version of `yamlresume` to avoid unexpected schema changes breaking the Claude prompt.
