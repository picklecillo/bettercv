from unittest.mock import MagicMock

import anthropic
from django.test import TestCase

from apps.compare.compare_service import CompareMetadataError, CompareService, JDMetadata


def _make_streaming_client(chunks: list[str]) -> MagicMock:
    fake_stream = MagicMock()
    fake_stream.__enter__ = lambda s: s
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_stream.text_stream = iter(chunks)
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.stream.return_value = fake_stream
    return client


def _make_tool_use_client(input_data: dict) -> MagicMock:
    tool_block = MagicMock()
    tool_block.type = "tool_use"
    tool_block.input = input_data
    response = MagicMock()
    response.content = [tool_block]
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.create.return_value = response
    return client


class ExtractMetadataTests(TestCase):

    def test_returns_jd_metadata_from_tool_use(self):
        client = _make_tool_use_client({
            "company": "Stripe",
            "title": "Senior Engineer",
            "score_low": 72,
            "score_high": 80,
        })
        service = CompareService(client)
        result = service.extract_metadata("## Estimated ATS Score 72–80 / 100\n...")
        self.assertIsInstance(result, JDMetadata)
        self.assertEqual(result.company, "Stripe")
        self.assertEqual(result.title, "Senior Engineer")
        self.assertEqual(result.score_low, 72)
        self.assertEqual(result.score_high, 80)

    def test_missing_tool_use_block_raises_error(self):
        response = MagicMock()
        response.content = []
        client = MagicMock(spec=anthropic.Anthropic)
        client.messages.create.return_value = response
        service = CompareService(client)
        with self.assertRaises(CompareMetadataError):
            service.extract_metadata("some analysis")


class StreamAnalysisTests(TestCase):

    def test_yields_chunks(self):
        client = _make_streaming_client(["Strong ", "match."])
        service = CompareService(client)
        result = "".join(service.stream_analysis("resume", "job desc"))
        self.assertEqual(result, "Strong match.")

    def test_passes_resume_and_jd_to_api(self):
        client = _make_streaming_client(["ok"])
        service = CompareService(client)
        list(service.stream_analysis("MY_RESUME", "MY_JD"))
        call_kwargs = client.messages.stream.call_args.kwargs
        user_content = call_kwargs["messages"][0]["content"]
        self.assertIn("MY_RESUME", user_content)
        self.assertIn("MY_JD", user_content)
