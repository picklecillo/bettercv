import anthropic
from django.conf import settings

SYSTEM_PROMPT = """You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Your job is to analyze how well a resume matches a job description and provide
a detailed, structured analysis in markdown format.

Always structure your response with these exact sections:
1. ## Estimated ATS Score (X–Y / 100)
2. ## Keyword Matches (table with: Requirement | Status | Notes)
3. ## Missing Keywords (table with: Missing Term | Why It Matters)
4. ## Quick Wins (specific, actionable improvements)
5. ## Overall Summary (2–3 sentences)

Be specific, honest, and actionable. Do not pad the analysis."""

USER_PROMPT = """Here is the resume:

{resume_text}

---

Here is the job description:

{jd_text}

---

Please provide a detailed ATS analysis."""


def get_ats_analysis(resume_text, jd_text):
    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT.format(
            resume_text=resume_text,
            jd_text=jd_text,
        )}],
    )
    return message.content[0].text
