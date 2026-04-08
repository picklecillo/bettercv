from collections.abc import Iterator

import anthropic

from apps.shared.claude import (
    MODEL,
    make_client,
    translate_api_error,
    translate_connection_error,
)

_MAX_TOKENS = 4000

_SYSTEM_PROMPT = """You are a resume conversion assistant. Convert the user's resume into valid rendercv YAML.

Output ONLY raw YAML — no prose, no markdown fences, no explanation. Start directly with the content after "cv:" (which is already prefilled). The output must be parseable by rendercv.

## Exact output format

Follow this structure precisely. Omit any section that has no data in the source resume.

  name: Jane Smith
  headline: Senior Software Engineer
  location: San Francisco, CA
  email: jane@example.com
  website: https://janesmith.dev
  social_networks:
    - network: LinkedIn
      username: janesmith
    - network: GitHub
      username: janesmith
  sections:
    summary:
      - Full stack engineer with 10+ years of experience across Python, JavaScript, and cloud infrastructure
    experience:
      - company: Acme Corp
        position: Senior Software Engineer
        start_date: "2021-03"
        end_date: present
        location: San Francisco, CA
        summary: Led a team through a high impact backend migration
        highlights:
          - Led migration of monolith to microservices, reducing deploy time by 60%
          - Mentored 4 junior engineers; 3 promoted within 18 months
      - company: Startup Inc
        position: Software Engineer
        start_date: "2018-06"
        end_date: "2021-02"
        location: New York, NY
        summary: Delivered on time at a fast paced startup
        highlights:
          - Built real-time analytics pipeline processing 50k events/sec
    education:
      - institution: University of California, Berkeley
        area: Computer Science
        degree: BS
        start_date: "2014-09"
        end_date: "2018-05"
        highlights:
          - "GPA: 3.8/4.0"
    projects:
      - name: OpenMetrics
        start_date: "2022"
        end_date: present
        summary: Open-source metrics aggregation library with 2k GitHub stars
        highlights:
          - Built plugin system supporting 12 data sources
    skills:
      - label: Languages
        details: Python, Go, TypeScript, SQL
      - label: Platforms
        details: AWS, Kubernetes, Terraform
    awards:
      - bullet: "AWS Certified Solutions Architect (2022)"
      - bullet: "Hackathon winner, TechCrunch Disrupt (2019)"

## Field rules

- dates: use YYYY-MM when month is known, YYYY when only year is known, "present" for current roles
- highlights: bullet points only — no sub-bullets, no markdown headers
- summary (on experience/projects): one line only, omit if redundant with highlights
- social_networks: supported networks are LinkedIn, GitHub, GitLab, Twitter, Instagram, ORCID, ResearchGate, YouTube, Google Scholar
- omit any field for which the source has no data
- do NOT invent information

## Bottom matter

Always end the output with exactly:
design:
  theme: classic
"""

_PREFILL = "cv:"


class WriterService:
    def __init__(self, client: anthropic.Anthropic) -> None:
        self._client = client

    def stream_yaml(self, resume_text: str) -> Iterator[str]:
        yield _PREFILL
        try:
            with self._client.messages.stream(
                model=MODEL,
                max_tokens=_MAX_TOKENS,
                system=_SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": resume_text},
                    {"role": "assistant", "content": _PREFILL},
                ],
            ) as s:
                yield from s.text_stream
        except anthropic.APIStatusError as e:
            raise translate_api_error(e) from e
        except anthropic.APIConnectionError as e:
            raise translate_connection_error(e) from e


def get_writer_service() -> WriterService:
    return WriterService(make_client())
