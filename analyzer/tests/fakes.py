from collections.abc import Iterator

from analyzer.claude import ClaudeService


class FakeClaudeService(ClaudeService):
    """Test double — no Anthropic client needed."""

    def __init__(self, response: str = "FAKE_ANALYSIS") -> None:
        self._response = response
        self.analyze_calls: list[dict] = []

    def analyze(self, resume_text: str, jd_text: str) -> str:
        self.analyze_calls.append({"resume_text": resume_text, "jd_text": jd_text})
        return self._response

    def stream(self, resume_text: str, jd_text: str) -> Iterator[str]:
        yield self._response
