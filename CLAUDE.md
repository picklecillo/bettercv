# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BetterCV is a Django + HTMX web app that analyzes how well a resume matches a job description using the Claude API. It streams structured ATS analysis back to the browser in real time. Stateless — no user accounts, no saved history.

## Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Configure environment
echo "ANTHROPIC_API_KEY=your_key_here" > .env

# Run development server
cd ats_analyzer
python manage.py runserver
```

## Common Commands

```bash
python manage.py runserver        # Start dev server at localhost:8000
python manage.py migrate          # Apply migrations
python manage.py shell            # Django shell
```

## Architecture

### Project Layout

```
ats_analyzer/
├── manage.py
├── requirements.txt
├── .env                          # ANTHROPIC_API_KEY
├── analyzer/                     # Main Django app
│   ├── views.py                  # Form view + streaming /analyze/ endpoint
│   ├── urls.py
│   ├── claude.py                 # Claude API client + prompts
│   ├── pdf.py                    # PDF text extraction via pdfplumber
│   └── templates/analyzer/
│       └── index.html            # Single-page HTMX UI
└── ats_analyzer/
    ├── settings.py               # Loads ANTHROPIC_API_KEY from .env
    └── urls.py
```

### Key Design Decisions

- **Streaming**: The `/analyze/` endpoint returns a `StreamingHttpResponse` (content-type `text/plain`), yielding Claude output chunks as they arrive. HTMX handles rendering via `hx-post` + `hx-target`.
- **SSE alternative**: Plain streaming may not render incrementally in all browsers — consider `hx-ext="sse"` with Server-Sent Events if word-by-word streaming doesn't work in practice.
- **PDF input**: `pdfplumber` extracts text from uploaded PDFs; if no PDF is uploaded, the view falls back to the pasted `resume_text` field.
- **No JS**: All interactivity is handled by HTMX. The form uses `hx-encoding="multipart/form-data"` to support file uploads.
- **Claude model**: `claude-sonnet-4-20250514`, max_tokens 2000. The system prompt enforces a fixed 5-section markdown structure (ATS Score, Keyword Matches, Missing Keywords, Quick Wins, Overall Summary).
- **Markdown rendering**: Claude's markdown output should be converted to HTML before insertion into the result div.

## Dependencies

- `django` — web framework
- `anthropic` — Claude API with streaming
- `pdfplumber` — PDF text extraction
- `markdown` — render Claude's markdown response to HTML
- `python-dotenv` — load `ANTHROPIC_API_KEY` from `.env`

## V2 Roadmap

- Resume Coach: multi-turn interview to rewrite work experience items
- Save analysis history (PostgreSQL)
- Compare multiple JDs against one resume
- Export analysis as PDF
- Deploy to Railway or Render
