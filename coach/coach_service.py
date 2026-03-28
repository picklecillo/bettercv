import anthropic
from collections.abc import Iterator
from dataclasses import dataclass
from django.conf import settings


class CoachParseError(Exception):
    pass


@dataclass
class WorkExperience:
    company: str
    title: str
    dates: str
    original_description: str


_EXTRACT_TOOL = {
    "name": "extract_work_experiences",
    "description": "Extract all work experience entries from a CV.",
    "input_schema": {
        "type": "object",
        "properties": {
            "experiences": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "company":              {"type": "string"},
                        "title":                {"type": "string"},
                        "dates":                {"type": "string"},
                        "original_description": {"type": "string"},
                    },
                    "required": ["company", "title", "dates", "original_description"],
                },
            }
        },
        "required": ["experiences"],
    },
}

_PARSE_PROMPT = """Extract every work experience entry from the CV below.
For each entry capture: company name, job title, dates (as written), and the full description text.

CV:
{cv_text}"""

_MODEL = "claude-sonnet-4-20250514"

_COACH_SYSTEM_PROMPT = """You are an expert resume coach helping a job seeker improve their CV.

The candidate's work experience entry you are coaching:

Company: {company}
Title: {title}
Dates: {dates}
Original description:
{original_description}

Your goal:
1. Ask targeted questions to draw out specific achievements, metrics, and impact from this role.
2. Once you have enough detail (typically after 2–4 questions), propose a paragraph-form rewrite that leads with impact and uses strong action verbs.
3. Incorporate any feedback the candidate gives in subsequent turns.

Start by asking one focused question about what the candidate actually accomplished in this role."""


class CoachService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def parse_cv(self, cv_text: str) -> list[WorkExperience]:
        response = self._client.messages.create(
            model=_MODEL,
            max_tokens=2000,
            tools=[_EXTRACT_TOOL],
            tool_choice={"type": "tool", "name": "extract_work_experiences"},
            messages=[{"role": "user", "content": _PARSE_PROMPT.format(cv_text=cv_text)}],
        )

        tool_block = next(
            (b for b in response.content if b.type == "tool_use"),
            None,
        )
        if tool_block is None:
            raise CoachParseError("Could not parse work experiences from your CV.")

        raw = tool_block.input.get("experiences", [])
        if not raw:
            raise CoachParseError("No work experiences found in your CV.")

        return [
            WorkExperience(
                company=e["company"],
                title=e["title"],
                dates=e["dates"],
                original_description=e["original_description"],
            )
            for e in raw
        ]


    def stream_reply(self, work_experience: WorkExperience, history: list[dict]) -> Iterator[str]:
        system_prompt = _COACH_SYSTEM_PROMPT.format(
            company=work_experience.company,
            title=work_experience.title,
            dates=work_experience.dates,
            original_description=work_experience.original_description,
        )
        with self._client.messages.stream(
            model=_MODEL,
            max_tokens=2000,
            system=system_prompt,
            messages=history,
        ) as s:
            yield from s.text_stream


def get_coach_service() -> CoachService:
    return CoachService(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))
