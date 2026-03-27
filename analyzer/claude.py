import anthropic
from collections.abc import Iterator
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

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 2000


class ClaudeService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def analyze(self, resume_text: str, jd_text: str) -> str:
        message = self._client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_PROMPT.format(
                resume_text=resume_text,
                jd_text=jd_text,
            )}],
        )
        return message.content[0].text

    def stream(self, resume_text: str, jd_text: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_PROMPT.format(
                resume_text=resume_text,
                jd_text=jd_text,
            )}],
        ) as s:
            yield from s.text_stream


def get_service() -> ClaudeService:
    return ClaudeService(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))
