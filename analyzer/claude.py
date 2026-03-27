import anthropic
from collections.abc import Iterator
from django.conf import settings


class ClaudeServiceError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


_ERROR_MESSAGES: dict[str, tuple[str, int]] = {
    "authentication_error":  ("Invalid API key. Check your ANTHROPIC_API_KEY.", 502),
    "permission_error":      ("Your API key doesn't have permission to use this model.", 502),
    "invalid_request_error": ("Bad request sent to Claude API.", 502),
    "not_found_error":       ("Claude model not found.", 502),
    "rate_limit_error":      ("Rate limit hit. Please wait a moment and try again.", 502),
    "api_error":             ("Claude API internal error. Please try again.", 502),
    "overloaded_error":      ("Claude is currently overloaded. Please try again shortly.", 502),
}

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
        try:
            message = self._client.messages.create(
                model=_MODEL,
                max_tokens=_MAX_TOKENS,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": USER_PROMPT.format(
                    resume_text=resume_text,
                    jd_text=jd_text,
                )}],
            )
        except anthropic.APIStatusError as e:
            raise self._translate(e) from e
        except anthropic.APIConnectionError as e:
            raise ClaudeServiceError(
                "Could not reach the Claude API. Check your internet connection.", 503
            ) from e
        return message.content[0].text

    @staticmethod
    def _translate(e: anthropic.APIStatusError) -> ClaudeServiceError:
        if "credit balance is too low" in str(e):
            return ClaudeServiceError(
                "Your Anthropic credit balance is too low. "
                "Please add credits at console.anthropic.com.",
                402,
            )
        error_type = (e.body or {}).get("error", {}).get("type", "")
        msg, status = _ERROR_MESSAGES.get(error_type, (str(e), 502))
        return ClaudeServiceError(msg, status)

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
