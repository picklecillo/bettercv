from unittest.mock import MagicMock

import anthropic
from django.test import TestCase

from apps.analyzer.claude import ClaudeService, ClaudeServiceError, _MODEL


class ClaudeServiceTests(TestCase):

    def _make_client(self, text: str) -> MagicMock:
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        fake = MagicMock(spec=anthropic.Anthropic)
        fake.messages.create.return_value = response
        return fake

    def _make_streaming_client(self, chunks: list[str]) -> MagicMock:
        fake_stream = MagicMock()
        fake_stream.__enter__ = lambda s: s
        fake_stream.__exit__ = MagicMock(return_value=False)
        fake_stream.text_stream = iter(chunks)
        fake = MagicMock(spec=anthropic.Anthropic)
        fake.messages.stream.return_value = fake_stream
        return fake

    def test_analyze_returns_response_text(self):
        service = ClaudeService(self._make_client("## ATS Score\n75/100"))
        result = service.analyze("my resume", "some job")
        self.assertEqual(result, "## ATS Score\n75/100")

    def test_analyze_passes_resume_and_jd_in_prompt(self):
        fake_client = self._make_client("ok")
        service = ClaudeService(fake_client)
        service.analyze("RESUME_CONTENT", "JD_CONTENT")

        call_kwargs = fake_client.messages.create.call_args.kwargs
        user_message = call_kwargs["messages"][0]["content"]
        self.assertIn("RESUME_CONTENT", user_message)
        self.assertIn("JD_CONTENT", user_message)

    def test_analyze_uses_correct_model(self):
        fake_client = self._make_client("ok")
        service = ClaudeService(fake_client)
        service.analyze("resume", "jd")

        call_kwargs = fake_client.messages.create.call_args.kwargs
        self.assertEqual(call_kwargs["model"], _MODEL)

    def test_stream_yields_chunks(self):
        service = ClaudeService(self._make_streaming_client(["## ATS", " Score\n", "75/100"]))
        result = "".join(service.stream("my resume", "some job"))
        self.assertEqual(result, "## ATS Score\n75/100")

    def test_analyze_raises_service_error_on_credit_exhaustion(self):
        sdk_error = anthropic.BadRequestError(
            message="Your credit balance is too low to access the Anthropic API.",
            response=MagicMock(status_code=400),
            body={"error": {"type": "invalid_request_error"}},
        )
        fake_client = MagicMock(spec=anthropic.Anthropic)
        fake_client.messages.create.side_effect = sdk_error
        service = ClaudeService(fake_client)

        with self.assertRaises(ClaudeServiceError) as ctx:
            service.analyze("resume", "jd")

        self.assertEqual(ctx.exception.status, 402)
        self.assertIn("console.anthropic.com", ctx.exception.message)

    def test_analyze_raises_service_error_on_rate_limit(self):
        sdk_error = anthropic.RateLimitError(
            message="Rate limited",
            response=MagicMock(status_code=429),
            body={"error": {"type": "rate_limit_error"}},
        )
        fake_client = MagicMock(spec=anthropic.Anthropic)
        fake_client.messages.create.side_effect = sdk_error
        service = ClaudeService(fake_client)

        with self.assertRaises(ClaudeServiceError) as ctx:
            service.analyze("resume", "jd")

        self.assertEqual(ctx.exception.status, 502)
        self.assertIn("Rate limit", ctx.exception.message)

    def test_analyze_raises_service_error_on_connection_failure(self):
        fake_client = MagicMock(spec=anthropic.Anthropic)
        fake_client.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())
        service = ClaudeService(fake_client)

        with self.assertRaises(ClaudeServiceError) as ctx:
            service.analyze("resume", "jd")

        self.assertEqual(ctx.exception.status, 503)
        self.assertIn("internet connection", ctx.exception.message)
