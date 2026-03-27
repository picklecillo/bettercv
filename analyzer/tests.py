import io
from unittest.mock import MagicMock, patch

import anthropic
from django.test import TestCase, Client


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


# ── claude.py ─────────────────────────────────────────────────────────────────

class GetAtsAnalysisTests(TestCase):

    def _make_response(self, text):
        content_block = MagicMock()
        content_block.text = text
        response = MagicMock()
        response.content = [content_block]
        return response

    def test_returns_response_text(self):
        from analyzer.claude import get_ats_analysis
        with patch("analyzer.claude.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = self._make_response("## ATS Score\n75/100")
            result = get_ats_analysis("my resume", "some job")

        self.assertEqual(result, "## ATS Score\n75/100")

    def test_passes_resume_and_jd_in_prompt(self):
        from analyzer.claude import get_ats_analysis
        with patch("analyzer.claude.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = self._make_response("ok")
            get_ats_analysis("RESUME_CONTENT", "JD_CONTENT")

            call_kwargs = MockClient.return_value.messages.create.call_args.kwargs
            user_message = call_kwargs["messages"][0]["content"]

        self.assertIn("RESUME_CONTENT", user_message)
        self.assertIn("JD_CONTENT", user_message)

    def test_uses_correct_model(self):
        from analyzer.claude import get_ats_analysis
        with patch("analyzer.claude.anthropic.Anthropic") as MockClient:
            MockClient.return_value.messages.create.return_value = self._make_response("ok")
            get_ats_analysis("resume", "jd")

            call_kwargs = MockClient.return_value.messages.create.call_args.kwargs

        self.assertEqual(call_kwargs["model"], "claude-sonnet-4-20250514")


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

    def test_get_not_allowed(self):
        response = self.client.get("/analyze/")
        self.assertEqual(response.status_code, 405)

    def test_missing_resume_returns_400(self):
        response = self.client.post("/analyze/", {"jd_text": "some job"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"resume", response.content.lower())

    def test_missing_jd_returns_400(self):
        response = self.client.post("/analyze/", {"resume_text": "my resume"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"job description", response.content.lower())

    def test_successful_analysis_returns_result(self):
        with patch("analyzer.views.get_ats_analysis", return_value="## ATS Score\n80/100"):
            response = self.client.post("/analyze/", {
                "resume_text": "my resume",
                "jd_text": "some job",
            })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"ATS Score", response.content)

    def test_credit_error_returns_402(self):
        error = anthropic.BadRequestError(
            message="Your credit balance is too low to access the Anthropic API.",
            response=MagicMock(status_code=400),
            body={"error": {"type": "invalid_request_error"}},
        )
        with patch("analyzer.views.get_ats_analysis", side_effect=error):
            response = self.client.post("/analyze/", {
                "resume_text": "my resume",
                "jd_text": "some job",
            })
        self.assertEqual(response.status_code, 402)
        self.assertIn(b"console.anthropic.com", response.content)

    def test_rate_limit_error_returns_502(self):
        error = anthropic.RateLimitError(
            message="Rate limited",
            response=MagicMock(status_code=429),
            body={"error": {"type": "rate_limit_error"}},
        )
        with patch("analyzer.views.get_ats_analysis", side_effect=error):
            response = self.client.post("/analyze/", {
                "resume_text": "my resume",
                "jd_text": "some job",
            })
        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Rate limit", response.content)

    def test_connection_error_returns_503(self):
        with patch("analyzer.views.get_ats_analysis", side_effect=anthropic.APIConnectionError(request=MagicMock())):
            response = self.client.post("/analyze/", {
                "resume_text": "my resume",
                "jd_text": "some job",
            })
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"internet connection", response.content)

    def test_pdf_upload_takes_priority_over_text(self):
        fake_pdf = io.BytesIO(b"fake pdf content")
        fake_pdf.name = "resume.pdf"

        with patch("analyzer.views.extract_text_from_pdf", return_value="PDF RESUME TEXT") as mock_pdf, \
             patch("analyzer.views.get_ats_analysis", return_value="result") as mock_claude:
            self.client.post("/analyze/", {
                "resume_text": "pasted text",
                "resume_pdf": fake_pdf,
                "jd_text": "some job",
            })

        mock_pdf.assert_called_once()
        mock_claude.assert_called_once_with("PDF RESUME TEXT", "some job")
