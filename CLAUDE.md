# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BetterCV is a Django + HTMX web app that analyzes how well a resume matches a job description using the Claude API. It streams structured ATS analysis back to the browser in real time. Stateless — no user accounts, no saved history.

## Setup

```bash
uv add <package>                  # Add dependencies (uv manages the venv)
cp .env.example .env              # Then fill in ANTHROPIC_API_KEY
```

## Common Commands

```bash
make run                          # Start dev server at localhost:8000
make test                         # Run full test suite
uv run python manage.py migrate   # Apply migrations
uv run python manage.py shell     # Django shell
uv run python manage.py test analyzer.tests.test_claude  # Run a single test file
```

## Architecture

### Project Layout

```
├── manage.py
├── pyproject.toml                # uv project + dependencies
├── .env                          # ANTHROPIC_API_KEY (not committed)
├── analyzer/                     # Main Django app
│   ├── views.py                  # Form view + /analyze/ endpoint
│   ├── urls.py
│   ├── claude.py                 # ClaudeService class + ClaudeServiceError
│   ├── pdf.py                    # PDF extraction + PdfExtractionError
│   └── templates/analyzer/
│       └── index.html            # Single-page HTMX UI (daisyUI + Tailwind via CDN)
│   └── tests/
│       ├── fakes.py              # FakeClaudeService (shared test double)
│       ├── test_claude.py
│       ├── test_pdf.py
│       └── test_views.py
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

## Implementation Plan

Phases tracked in `plans/ats-analyzer-v1.md`. Current status: Phase 2 (batch analysis) complete.

## V2 Roadmap

- Resume Coach: multi-turn interview to rewrite work experience items
- Save analysis history (PostgreSQL)
- Compare multiple JDs against one resume
- Export analysis as PDF
- Deploy to Railway or Render
