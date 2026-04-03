import anthropic
from collections.abc import Iterator
from dataclasses import dataclass

from apps.analyzer.claude import ATS_SYSTEM_PROMPT, ATS_USER_PROMPT
from apps.shared.claude import (
    MODEL,
    make_client,
    translate_api_error,
    translate_connection_error,
)

_MAX_TOKENS = 2000


class CompareMetadataError(Exception):
    pass


@dataclass
class JDMetadata:
    company: str
    title: str
    score_low: int
    score_high: int


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

_METADATA_PROMPT = """Here is the job description followed by a completed ATS analysis. Extract the company name, job title, and ATS score range.

Job description:
{jd_text}

ATS analysis:
{analysis_text}"""


class CompareService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def stream_analysis(self, resume_text: str, jd_text: str) -> Iterator[str]:
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

    def extract_metadata(self, analysis_text: str, jd_text: str = "") -> JDMetadata:
        try:
            response = self._client.messages.create(
                model=MODEL,
                max_tokens=256,
                tools=[_METADATA_TOOL],
                tool_choice={"type": "tool", "name": "extract_jd_metadata"},
                messages=[{"role": "user", "content": _METADATA_PROMPT.format(
                    analysis_text=analysis_text,
                    jd_text=jd_text,
                )}],
            )
        except anthropic.APIStatusError as e:
            raise CompareMetadataError(translate_api_error(e).message) from e
        except anthropic.APIConnectionError as e:
            raise CompareMetadataError(translate_connection_error(e).message) from e

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
    return CompareService(make_client())
