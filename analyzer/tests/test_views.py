import io
from unittest.mock import MagicMock, patch

from django.test import TestCase

from analyzer.claude import ClaudeServiceError
from analyzer.pdf import PdfExtractionError
from analyzer.tests.fakes import FakeClaudeService


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
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=ClaudeServiceError(
            "Your Anthropic credit balance is too low. Please add credits at console.anthropic.com.", 402
        ))
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 402)
        self.assertIn(b"console.anthropic.com", response.content)

    def test_rate_limit_error_returns_502(self):
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=ClaudeServiceError(
            "Rate limit hit. Please wait a moment and try again.", 502
        ))
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 502)
        self.assertIn(b"Rate limit", response.content)

    def test_connection_error_returns_503(self):
        fake = FakeClaudeService()
        fake.analyze = MagicMock(side_effect=ClaudeServiceError(
            "Could not reach the Claude API. Check your internet connection.", 503
        ))
        response = self._post({"resume_text": "my resume", "jd_text": "some job"}, service=fake)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b"internet connection", response.content)

    def test_unreadable_pdf_returns_400(self):
        fake_pdf = io.BytesIO(b"bad pdf")
        fake_pdf.name = "resume.pdf"

        with patch("analyzer.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Could not read the PDF file: corrupt")), \
             patch("analyzer.views.get_service", return_value=FakeClaudeService()):
            response = self.client.post("/analyze/", {
                "resume_pdf": fake_pdf,
                "jd_text": "some job",
            })

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"Could not read", response.content)

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
