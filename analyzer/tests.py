import io
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import anthropic
from django.test import TestCase

from analyzer.claude import ClaudeService, _MODEL


# ── Helpers ───────────────────────────────────────────────────────────────────

class FakeClaudeService(ClaudeService):
    """Test double — no Anthropic client needed."""

    def __init__(self, response: str = "FAKE_ANALYSIS") -> None:
        self._response = response
        self.analyze_calls: list[dict] = []

    def analyze(self, resume_text: str, jd_text: str) -> str:
        self.analyze_calls.append({"resume_text": resume_text, "jd_text": jd_text})
        return self._response

    def stream(self, resume_text: str, jd_text: str) -> Iterator[str]:
        yield from self._response


# ── pdf.py ────────────────────────────────────────────────────────────────────

class ExtractTextFromPdfTests(TestCase):

    def test_extracts_text_from_pages(self):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page one text"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("analyzer.pdf.pdfplumber.open", return_value=mock_pdf):
            from analyzer.pdf import extract_text_from_pdf
            result = extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertEqual(result, "Page one text")

    def test_skips_pages_with_no_text(self):
        page_with_text = MagicMock()
        page_with_text.extract_text.return_value = "Real content"
        page_empty = MagicMock()
        page_empty.extract_text.return_value = None
        mock_pdf = MagicMock()
        mock_pdf.pages = [page_empty, page_with_text]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("analyzer.pdf.pdfplumber.open", return_value=mock_pdf):
            from analyzer.pdf import extract_text_from_pdf
            result = extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertEqual(result, "Real content")

    def test_returns_empty_string_for_empty_pdf(self):
        mock_pdf = MagicMock()
        mock_pdf.pages = []
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("analyzer.pdf.pdfplumber.open", return_value=mock_pdf):
            from analyzer.pdf import extract_text_from_pdf
            result = extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertEqual(result, "")


# ── ClaudeService ─────────────────────────────────────────────────────────────

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


# ── views.py ──────────────────────────────────────────────────────────────────

class IndexViewTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_get_returns_form(self):
        response = self.client.get("/")
        self.assertContains(response, 'name="resume_text"')
        self.assertContains(response, 'name="jd_text"')
        self.assertContains(response, 'name="resume_pdf"')


class AnalyzeViewTests(TestCase):

    def _post(self, data, service=None):
        fake = service or FakeClaudeService()
        with patch("analyzer.views.get_service", return_value=fake):
            return self.client.post("/analyze/", data)

    def test_get_not_allowed(self):
        response = self.client.get("/analyze/")
        self.assertEqual(response.status_code, 405)

    def test_missing_resume_returns_400(self):
        response = self._post({"jd_text": "some job"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"resume", response.content.lower())

    def test_missing_jd_returns_400(self):
        response = self._post({"resume_text": "my resume"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"job description", response.content.lower())

    def test_successful_analysis_returns_result(self):
        response = self._post(
            {"resume_text": "my resume", "jd_text": "some job"},
            service=FakeClaudeService("## ATS Score\n80/100"),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ATS Score", response.content)

    def test_resume_and_jd_forwarded_to_service(self):
        fake = FakeClaudeService()
        self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(fake.analyze_calls[0]["resume_text"], "my resume")
        self.assertEqual(fake.analyze_calls[0]["jd_text"], "some job")

    def test_credit_error_returns_402(self):
        error = anthropic.BadRequestError(
            message="Your credit balance is too low to access the Anthropic API.",
            response=MagicMock(status_code=400),
            body={"error": {"type": "invalid_request_error"}},
        )
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=error)
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 402)
        self.assertIn(b"console.anthropic.com", response.content)

    def test_rate_limit_error_returns_502(self):
        error = anthropic.RateLimitError(
            message="Rate limited",
            response=MagicMock(status_code=429),
            body={"error": {"type": "rate_limit_error"}},
        )
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=error)
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Rate limit", response.content)

    def test_connection_error_returns_503(self):
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=anthropic.APIConnectionError(request=MagicMock()))
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"internet connection", response.content)

    def test_pdf_upload_takes_priority_over_text(self):
        fake_pdf = io.BytesIO(b"fake pdf content")
        fake_pdf.name = "resume.pdf"
        fake = FakeClaudeService()

        with patch("analyzer.views.extract_text_from_pdf", return_value="PDF RESUME TEXT") as mock_pdf, \
             patch("analyzer.views.get_service", return_value=fake):
            self.client.post("/analyze/", {
                "resume_text": "pasted text",
                "resume_pdf": fake_pdf,
                "jd_text": "some job",
            })

        mock_pdf.assert_called_once()
        self.assertEqual(fake.analyze_calls[0]["resume_text"], "PDF RESUME TEXT")
