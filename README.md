# BetterCV — https://bettercv.fly.dev/

AI-powered career toolkit built with Django, HTMX, and Claude. Upload your resume once and use four tools — ATS Analyzer, Resume Coach, Multi-JD Compare, and Resume Writer.

## Tools

- **ATS Analyzer** — score your resume against a job description with keyword and quick-win feedback
- **Resume Coach** — interactive per-role coaching that rewrites bullet points into achievement-focused language
- **Multi-JD Compare** — add up to 10 job descriptions and see a scored comparison table at a glance
- **Resume Writer** — convert your resume to a structured RenderCV YAML and download a polished PDF

## Setup

```bash
cp .env.example .env          # add ANTHROPIC_API_KEY
uv sync                       # install dependencies
uv run python manage.py migrate
make run                      # http://localhost:8000
```

## Development

```bash
make test                     # run all tests
uv run python manage.py test apps.writer.tests.test_views   # single module
uv add <package>              # add a dependency
```

## Stack

- **Backend** — Django 5, SQLite sessions (no user accounts)
- **AI** — Anthropic Claude (`claude-sonnet-4-20250514`) via streaming and tool use
- **PDF** — RenderCV (Typst-based, no system dependencies) + pdfplumber for extraction
- **Frontend** — HTMX 2, daisyUI 5, Tailwind CSS (CDN, no build step)
