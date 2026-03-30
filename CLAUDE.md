# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BetterCV is a Django + HTMX web app with four tools: ATS Analyzer, Resume Coach, Multi-JD Compare, and Resume Writer. All use the Claude API with SSE streaming. Stateless — no user accounts, no saved history (DB-backed sessions via SQLite).

## Setup

```bash
uv add <package>                  # Add dependencies (uv manages the venv)
cp .env.example .env              # Then fill in ANTHROPIC_API_KEY
```

## Common Commands

```bash
make run                                                       # Start dev server at localhost:8000
make test                                                      # Run full test suite
uv run python manage.py migrate                                # Apply migrations
uv run python manage.py shell                                  # Django shell
uv run python manage.py test apps.writer.tests.test_views      # Run a single test module (note apps. prefix)
```

## Architecture

### Project Layout

```
├── manage.py
├── pyproject.toml                # uv project + dependencies
├── .env                          # ANTHROPIC_API_KEY (not committed)
├── shared/                       # Cross-cutting utilities
│   ├── pdf.py                    # extract_text_from_pdf() + PdfExtractionError (moved from analyzer)
│   └── session.py                # get_shared_resume()
├── analyzer/                     # ATS Analyzer app
│   ├── views.py                  # Form view + /analyze/ endpoint
│   ├── claude.py                 # ClaudeService class + ClaudeServiceError
│   ├── pdf.py                    # PDF extraction + PdfExtractionError
│   └── templates/analyzer/index.html
│   └── tests/
│       ├── fakes.py              # FakeClaudeService
│       ├── test_claude.py
│       ├── test_pdf.py
│       └── test_views.py
├── coach/                        # Resume Coach app (multi-turn AI coaching)
│   ├── coach_service.py          # CoachService: parse_cv() (tool use) + stream_reply()
│   └── tests/fakes.py            # FakeCoachService
├── compare/                      # Multi-JD Compare app (stream N analyses, summary table)
│   ├── compare_service.py        # CompareService: stream_analysis() + extract_metadata() (tool use)
│   └── tests/fakes.py            # FakeCompareService
├── writer/                       # Resume Writer app (SSE YAML stream + rendercv PDF/HTML)
│   ├── views.py                  # index, parse, stream, build, render_preview
│   ├── writer_service.py         # WriterService: stream_yaml() with assistant prefill
│   ├── rendercv_builder.py       # RenderCVBuilder: build_pdf() + render_html() via subprocess
│   └── tests/fakes.py            # FakeRenderCVBuilder
└── ats_analyzer/
    ├── settings.py               # Loads ANTHROPIC_API_KEY via python-dotenv
    └── urls.py
```

### Key Design Decisions

- **Package manager**: `uv` — use `uv run` to prefix all Python/Django commands.
- **SSE streaming**: The plan calls for `hx-ext="sse"` Server-Sent Events from day one (not plain `StreamingHttpResponse`). Phase 3 of `plans/ats-analyzer-v1.md`.
- **Service layer**: `ClaudeService` in `claude.py` owns all Anthropic API interaction. It takes an `anthropic.Anthropic` client via `__init__`. Production code calls `get_service()` to get an instance.
- **App-level exceptions**: `ClaudeService` translates SDK exceptions into `ClaudeServiceError(message, status)`. `pdf.py` raises `PdfExtractionError` for unreadable/empty PDFs. Views catch these — they never import `anthropic` directly.
- **PDF input**: PDF upload takes priority over pasted text. `pdfplumber` extracts text; raises `PdfExtractionError` (not silent empty string) if the PDF is unreadable or image-based.
- **Claude model**: `claude-sonnet-4-20250514`, max_tokens 2000. System prompt enforces a fixed 5-section markdown structure (ATS Score, Keyword Matches, Missing Keywords, Quick Wins, Overall Summary).
- **Frontend**: daisyUI + Tailwind loaded via CDN in `index.html`. No build step. HTMX handles all interactivity; form uses `hx-encoding="multipart/form-data"` for file uploads.
- **SSE + wrap pattern**: `hx-ext="sse"`, `sse-connect`, and `sse-close` must be on an outer element that survives content replacement. When a `wrap` SSE event replaces an inner container, it destroys all `sse-swap` listeners inside it — emit any remaining SSE events (e.g. `metadata`) *before* `wrap`. Without this, the `EventSource` is orphaned and corrupts SSE state for subsequent cards.
- **OOB table rows (HTMX 2)**: `<tr>` elements cannot be reliably inserted via `hx-swap-oob` — they are stripped during fragment parsing. Make `<tr>` the *primary* swap target (`hx-target="#tbody-id"` + `hx-swap="beforeend"`); HTMX wraps primary content in `<template>` before parsing, which preserves table elements. Put other fragments in OOB `<div>` wrappers (div-into-div works fine).
- **session.save() in generators**: Django's session middleware runs `process_response` *before* streaming content is consumed. Any session mutations inside a `StreamingHttpResponse` generator must call `request.session.save()` explicitly.
- **Nonce pattern**: POST endpoints store `{jd_id, resume_text, jd_text, ...}` under `session[nonce]` (a UUID key). The stream GET endpoint pops the nonce before the generator starts — saved by middleware, preventing reuse even if the generator errors.
- **rendercv output paths**: rendercv names output files after `cv.name` in the YAML, not the input filename. Always pass `--pdf-path out.pdf` and `--html-path out.html` to get predictable paths.
- **rendercv HTML requires markdown**: `--dont-generate-markdown` also silently disables HTML. For HTML-only: use `--dont-generate-typst --dont-generate-pdf --dont-generate-png`.
- **rendercv errors go to stdout**: rendercv uses `rich` and prints validation errors to stdout, not stderr. Capture both: `result.stderr.strip() or result.stdout.strip()`.
- **Anthropic prefill trailing whitespace**: Assistant prefill content must not end with whitespace — `"cv:\n"` is rejected with a 400. Use `"cv:"` and let Claude's first token supply the newline.
- **SSE error + follow-up action**: If an SSE error event is followed immediately by a `done` event that triggers a fetch, the fetch's error will overwrite the SSE error in the UI. Track a `hadStreamError` flag and skip the follow-up action if set.

### Testing Patterns

- Inject `FakeClaudeService` from `analyzer.tests.fakes` into view tests via `patch("analyzer.views.get_service", return_value=fake)`.
- Test `ClaudeService` directly by passing a `MagicMock(spec=anthropic.Anthropic)` to its constructor — no module-level patching needed.
- Views never raise SDK exceptions; test error paths by raising `ClaudeServiceError` or `PdfExtractionError` from the fake.

## Dependencies

- `django` — web framework
- `anthropic` — Claude API with streaming
- `pdfplumber` — PDF text extraction
- `markdown` — render Claude's markdown response to HTML
- `python-dotenv` — load `ANTHROPIC_API_KEY` from `.env`
- `rendercv[full]` — PDF/HTML generation (requires Python ≥ 3.12, uses Typst, no system libs needed)

## V2 Roadmap

All plans tracked in `plans/`. All four features are complete (153 tests green).

Remaining roadmap:
- Export analysis as PDF
- Save analysis history (PostgreSQL)
- Deploy to Railway or Render
