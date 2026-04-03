import anthropic
from collections.abc import Iterator

from apps.shared.claude import (
    MODEL,
    ClaudeServiceError,
    make_client,
    translate_api_error,
    translate_connection_error,
)

# Re-export for backward compatibility with existing imports
__all__ = ["ClaudeService", "ClaudeServiceError", "get_service"]

# Backward-compat alias used in tests
_MODEL = MODEL

ATS_SYSTEM_PROMPT = """You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Your job is to analyze how well a resume matches a job description and provide
a detailed, structured analysis in markdown format.

Always structure your response with these exact sections:
1. ## Estimated ATS Score (X–Y / 100)
2. ## Keyword Matches (table with: Requirement | Status | Notes)
3. ## Missing Keywords (table with: Missing Term | Why It Matters)
4. ## Quick Wins (specific, actionable improvements)
5. ## Overall Summary (2–3 sentences)

Be specific, honest, and actionable. Do not pad the analysis."""

ATS_USER_PROMPT = """Here is the resume:

{resume_text}

---

Here is the job description:

{jd_text}

---

Please provide a detailed ATS analysis."""

# Legacy names kept for any direct imports
SYSTEM_PROMPT = ATS_SYSTEM_PROMPT
USER_PROMPT = ATS_USER_PROMPT

_MAX_TOKENS = 2000


class ClaudeService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def analyze(self, resume_text: str, jd_text: str) -> str:
        try:
            message = self._client.messages.create(
                model=MODEL,
                max_tokens=_MAX_TOKENS,
                system=ATS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": ATS_USER_PROMPT.format(
                    resume_text=resume_text,
                    jd_text=jd_text,
                )}],
            )
        except anthropic.APIStatusError as e:
            raise translate_api_error(e) from e
        except anthropic.APIConnectionError as e:
            raise translate_connection_error(e) from e
        return message.content[0].text

    def stream(self, resume_text: str, jd_text: str) -> Iterator[str]:
        try:
            with self._client.messages.stream(
                model=MODEL,
                max_tokens=_MAX_TOKENS,
                system=ATS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": ATS_USER_PROMPT.format(
                    resume_text=resume_text,
                    jd_text=jd_text,
                )}],
            ) as s:
                yield from s.text_stream
        except anthropic.APIStatusError as e:
            raise translate_api_error(e) from e
        except anthropic.APIConnectionError as e:
            raise translate_connection_error(e) from e


def get_service() -> ClaudeService:
    return ClaudeService(make_client())
