# ATS Analyzer — V1 Project Spec

## Overview
A Django + HTMX web app that takes a resume and a job description, calls the Claude API, and streams back a structured ATS analysis rendered as HTML. Runs locally for now, stateless (no database beyond Django's default SQLite).

---

## Features (V1)
- Paste resume as text **or** upload a PDF
- Paste a job description as text
- Stream the Claude API response back word by word via HTMX
- Render Claude's markdown output as HTML
- No user accounts, no saved history

---

## Tech Stack
- **Django** — web framework
- **HTMX** — streaming response handling, no JS frontend needed
- **Anthropic Python SDK** — Claude API with streaming
- **pdfplumber** — PDF text extraction (more reliable than PyPDF2)
- **markdown** — render Claude's markdown output to HTML
- **python-dotenv** — manage the API key locally

---

## Project Structure
```
ats_analyzer/
├── manage.py
├── requirements.txt
├── .env                         # ANTHROPIC_API_KEY goes here
├── analyzer/
│   ├── views.py                 # main view + streaming endpoint
│   ├── urls.py
│   ├── claude.py                # Claude API logic + prompt
│   ├── pdf.py                   # PDF text extraction
│   └── templates/
│       └── analyzer/
│           └── index.html       # main UI template
└── ats_analyzer/
    ├── settings.py
    └── urls.py
```

---

## Requirements (requirements.txt)
```
django
anthropic
pdfplumber
markdown
python-dotenv
```

---

## User Flow
1. User opens the app at `http://localhost:8000`
2. Fills in the form:
   - Resume: paste text **or** upload a PDF file
   - Job Description: paste text
3. Submits the form via HTMX POST to `/analyze/`
4. Django extracts PDF text if a file was uploaded
5. Calls Claude API with streaming enabled
6. Streams markdown chunks back to the browser in real time
7. HTMX appends chunks to a result div as they arrive
8. Once complete, full markdown is rendered to HTML

---

## Claude Prompt Structure

### System prompt
```
You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Your job is to analyze how well a resume matches a job description and provide
a detailed, structured analysis in markdown format.

Always structure your response with these exact sections:
1. ## Estimated ATS Score (X–Y / 100)
2. ## Keyword Matches (table with: Requirement | Status | Notes)
3. ## Missing Keywords (table with: Missing Term | Why It Matters)
4. ## Quick Wins (specific, actionable improvements)
5. ## Overall Summary (2–3 sentences)

Be specific, honest, and actionable. Do not pad the analysis.
```

### User prompt
```
Here is the resume:

{resume_text}

---

Here is the job description:

{jd_text}

---

Please provide a detailed ATS analysis.
```

---

## Key Implementation Notes

### PDF Extraction (pdf.py)
```python
import pdfplumber

def extract_text_from_pdf(file):
    with pdfplumber.open(file) as pdf:
        return "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
```

### Claude Streaming (claude.py)
```python
import anthropic
from django.conf import settings

client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

def stream_ats_analysis(resume_text, jd_text):
    with client.messages.stream(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT.format(
            resume_text=resume_text,
            jd_text=jd_text
        )}]
    ) as stream:
        for text in stream.text_stream:
            yield text
```

### Streaming View (views.py)
```python
from django.http import StreamingHttpResponse
from django.views.decorators.http import require_POST
from .claude import stream_ats_analysis
from .pdf import extract_text_from_pdf

@require_POST
def analyze(request):
    jd_text = request.POST.get("jd_text", "")
    
    if request.FILES.get("resume_pdf"):
        resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
    else:
        resume_text = request.POST.get("resume_text", "")

    def generate():
        buffer = ""
        for chunk in stream_ats_analysis(resume_text, jd_text):
            buffer += chunk
            yield chunk
        # optionally render full markdown at the end

    return StreamingHttpResponse(generate(), content_type="text/plain")
```

### HTMX Streaming (index.html)
```html
<form hx-post="/analyze/"
      hx-target="#result"
      hx-swap="innerHTML"
      hx-encoding="multipart/form-data">

  <textarea name="resume_text" placeholder="Paste resume here..."></textarea>
  <input type="file" name="resume_pdf" accept=".pdf">
  <textarea name="jd_text" placeholder="Paste job description here..."></textarea>
  <button type="submit">Analyze</button>
</form>

<div id="result"></div>
```

> **Note:** HTMX streaming requires `hx-swap="innerHTML"` and the response to be streamed as `text/plain`. For true word-by-word streaming with HTMX, look into Server-Sent Events (SSE) with `hx-ext="sse"` as an alternative approach if plain streaming doesn't render incrementally in the browser.

---

## Environment Setup
```bash
# .env
ANTHROPIC_API_KEY=your_key_here
```

```python
# settings.py
from dotenv import load_dotenv
import os
load_dotenv()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
```

---

## Build Order
1. Django project setup + basic form view rendering
2. PDF extraction with pdfplumber
3. Claude streaming integration
4. HTMX wiring for streaming response
5. Markdown rendering to HTML
6. Basic styling

---

## V2 Ideas (after V1 ships)
- Resume Coach feature: multi-turn interview to rewrite each work experience item
- Save analysis history with PostgreSQL
- Compare multiple JDs against one resume
- Export analysis as PDF
- Deploy to Railway or Render
