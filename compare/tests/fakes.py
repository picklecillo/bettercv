from collections.abc import Iterator

from compare.compare_service import CompareMetadataError, CompareService, JDMetadata

FAKE_METADATA = JDMetadata(
    company="Acme Corp",
    title="Senior Engineer",
    score_low=70,
    score_high=82,
)


class FakeCompareService(CompareService):
    """Test double — no Anthropic client needed."""

    def __init__(self, metadata=None, raise_metadata=None):
        self._metadata = metadata if metadata is not None else FAKE_METADATA
        self._raise_metadata = raise_metadata

    def stream_analysis(self, resume_text: str, jd_text: str) -> Iterator[str]:
        yield "Strong match for this role."

    def extract_metadata(self, analysis_text: str, jd_text: str = "") -> JDMetadata:
        if self._raise_metadata:
            raise self._raise_metadata
        return self._metadata
