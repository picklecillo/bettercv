import anthropic
from collections.abc import Iterator
from dataclasses import dataclass
from django.conf import settings


class CompareMetadataError(Exception):
    pass


@dataclass
class JDMetadata:
    company: str
    title: str
    score_low: int
    score_high: int


_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 2000

_SYSTEM_PROMPT = """You are an expert ATS (Applicant Tracking System) analyst and resume coach.
Your job is to analyze how well a resume matches a job description and provide
a detailed, structured analysis in markdown format.

Always structure your response with these exact sections:
1. ## Estimated ATS Score (X–Y / 100)
2. ## Keyword Matches (table with: Requirement | Status | Notes)
3. ## Missing Keywords (table with: Missing Term | Why It Matters)
4. ## Quick Wins (specific, actionable improvements)
5. ## Overall Summary (2–3 sentences)

Be specific, honest, and actionable. Do not pad the analysis."""

_USER_PROMPT = """Here is the resume:

{resume_text}

---

Here is the job description:

{jd_text}

---

Please provide a detailed ATS analysis."""

_METADATA_TOOL = {
    "name": "extract_jd_metadata",
    "description": "Extract the job title, company name, and ATS score range from a completed ATS analysis.",
    "input_schema": {
        "type": "object",
        "properties": {
            "company":     {"type": "string", "description": "Company name from the job description"},
            "title":       {"type": "string", "description": "Job title from the job description"},
            "score_low":   {"type": "integer", "description": "Lower bound of the ATS score range"},
            "score_high":  {"type": "integer", "description": "Upper bound of the ATS score range"},
        },
        "required": ["company", "title", "score_low", "score_high"],
    },
}

_METADATA_PROMPT = """Here is a completed ATS analysis. Extract the company name, job title, and ATS score range.

{analysis_text}"""


class CompareService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def stream_analysis(self, resume_text: str, jd_text: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _USER_PROMPT.format(
                resume_text=resume_text,
                jd_text=jd_text,
            )}],
        ) as s:
            yield from s.text_stream

    def extract_metadata(self, analysis_text: str) -> JDMetadata:
        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=256,
            tools=[_METADATA_TOOL],
            tool_choice={"type": "tool", "name": "extract_jd_metadata"},
            messages=[{"role": "user", "content": _METADATA_PROMPT.format(
                analysis_text=analysis_text,
            )}],
        )
        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise CompareMetadataError("Could not extract metadata from analysis.")
        i = tool_block.input
        return JDMetadata(
            company=i["company"],
            title=i["title"],
            score_low=i["score_low"],
            score_high=i["score_high"],
        )


def get_compare_service() -> CompareService:
    return CompareService(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))
