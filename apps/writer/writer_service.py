from collections.abc import Iterator

import anthropic
from django.conf import settings

_MODEL = "claude-sonnet-4-20250514"
_MAX_TOKENS = 4000

_SYSTEM_PROMPT = """You are a resume conversion assistant. Convert the user's resume into valid simple-resume YAML format.

Output ONLY the raw YAML — no prose, no markdown code fences, no explanation. The output must be valid YAML that can be parsed directly.

## simple-resume YAML schema

Required fields:
  full_name: "Full Name"
  email: "email@example.com"
  template: resume_no_bars   # always use this value

Required sections (always include both, even if empty):
  titles:
    contact: Contact
    expertise: Expertise
    certification: Certifications
    keyskills: Key Skills

  config:
    theme_color: '#0395DE'
    sidebar_color: '#003A70'
    sidebar_text_color: '#FFFFFF'

Optional header fields:
  phone: "+1 555 000 0000"
  web: "https://example.com"
  linkedin: "https://linkedin.com/in/handle"
  address:
    - "City, State"
    - "Country"

Optional sidebar sections (list of strings):
  description: "One-paragraph professional summary."
  expertise:
    - Core Competency One
    - Core Competency Two
  keyskills:
    - Skill One
    - Skill Two
  certification:
    - Certification Name

Body sections — each entry uses this structure:
  body:
    Experience:
      - title: "Job Title"
        company: "Company Name"
        start: "2020"          # YYYY or YYYY-MM
        end: "Present"         # YYYY, YYYY-MM, or "Present"
        title_link: "https://..."   # optional
        company_link: "https://..."  # optional
        description: |
          Markdown-formatted description.
          - Use bullet points for achievements
          - **Bold** key metrics
    Education:
      - title: "Degree"
        company: "University Name"
        start: "2014"
        end: "2018"
        description: "Major, GPA, honours, etc."
    Projects:
      - title: "Project Name"
        company: "Context or Employer"
        start: "2022"
        end: "2023"
        description: |
          What you built and why it mattered.
    Certifications:
      - title: "Certification Name"
        company: "Issuing Body"
        start: "2021"
        description: "Brief note."

Rules:
- Infer and populate as many fields as possible from the source resume.
- Preserve all dates exactly as they appear in the source.
- Use the original wording for descriptions; improve formatting but not content.
- If a section is absent in the source resume, omit it entirely.
- Do NOT invent information not present in the source resume.
"""


class WriterService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def stream_yaml(self, resume_text: str) -> Iterator[str]:
        with self._client.messages.stream(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": resume_text}],
        ) as s:
            yield from s.text_stream


def get_writer_service() -> WriterService:
    return WriterService(anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY))
