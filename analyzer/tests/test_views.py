import io
import uuid
from unittest.mock import MagicMock, patch

from django.test import TestCase

from analyzer.claude import ClaudeServiceError
from shared.pdf import PdfExtractionError
from analyzer.tests.fakes import FakeClaudeService


class IndexViewTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/analyzer/")
        self.assertEqual(response.status_code, 200)

    def test_get_returns_form(self):
        response = self.client.get("/analyzer/")
        self.assertContains(response, 'name="resume_text"')
        self.assertContains(response, 'name="jd_text"')
        self.assertContains(response, 'name="resume_pdf"')

    def test_get_prefills_resume_from_shared_session(self):
        session = self.client.session
        session["shared_resume"] = {
            "resume_text": "My shared resume",
            "resume_filename": None,
            "version": 1,
        }
        session.save()
        response = self.client.get("/analyzer/")
        self.assertContains(response, "My shared resume")

    def test_get_no_prefill_when_no_shared_session(self):
        response = self.client.get("/analyzer/")
        self.assertNotContains(response, "Change resume")


class AnalyzeViewTests(TestCase):

    def test_get_not_allowed(self):
        response = self.client.get("/analyzer/analyze/")
        self.assertEqual(response.status_code, 405)

    def test_missing_resume_returns_error(self):
        response = self.client.post("/analyzer/analyze/", {"jd_text": "some job"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)
        self.assertIn(b"resume", response.content.lower())

    def test_missing_jd_returns_error(self):
        response = self.client.post("/analyzer/analyze/", {"resume_text": "my resume"})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)
        self.assertIn(b"job description", response.content.lower())

    def test_valid_post_returns_sse_container(self):
        response = self.client.post("/analyzer/analyze/", {
            "resume_text": "my resume",
            "jd_text": "some job",
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sse-connect", response.content)
        self.assertIn(b"sse-swap", response.content)
        self.assertIn(b"/analyzer/analyze/stream/", response.content)

    def test_valid_post_stores_data_in_session(self):
        self.client.post("/analyzer/analyze/", {"resume_text": "my resume", "jd_text": "some job"})
        session_values = [
            v for v in self.client.session.values()
            if isinstance(v, dict) and "resume_text" in v and "jd_text" in v
        ]
        self.assertEqual(len(session_values), 1)
        self.assertEqual(session_values[0]["resume_text"], "my resume")
        self.assertEqual(session_values[0]["jd_text"], "some job")

    def test_unreadable_pdf_returns_error(self):
        fake_pdf = io.BytesIO(b"bad pdf")
        fake_pdf.name = "resume.pdf"

        with patch("analyzer.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Could not read the PDF file: corrupt")):
            response = self.client.post("/analyzer/analyze/", {
                "resume_pdf": fake_pdf,
                "jd_text": "some job",
            })

        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)
        self.assertIn(b"Could not read", response.content)

    def test_pdf_upload_takes_priority_over_text(self):
        fake_pdf = io.BytesIO(b"fake pdf content")
        fake_pdf.name = "resume.pdf"

        with patch("analyzer.views.extract_text_from_pdf", return_value="PDF RESUME TEXT") as mock_pdf:
            self.client.post("/analyzer/analyze/", {
                "resume_text": "pasted text",
                "resume_pdf": fake_pdf,
                "jd_text": "some job",
            })

        mock_pdf.assert_called_once()
        session_values = [v for v in self.client.session.values()
                          if isinstance(v, dict) and "resume_text" in v and "jd_text" in v]
        self.assertEqual(session_values[0]["resume_text"], "PDF RESUME TEXT")


class StreamViewTests(TestCase):

    def _setup_session(self, resume_text="my resume", jd_text="some job"):
        key = str(uuid.uuid4())
        session = self.client.session
        session[key] = {"resume_text": resume_text, "jd_text": jd_text}
        session.save()
        return key

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def test_missing_key_returns_400(self):
        response = self.client.get("/analyzer/analyze/stream/")
        self.assertEqual(response.status_code, 400)

    def test_unknown_key_returns_400(self):
        response = self.client.get("/analyzer/analyze/stream/?key=nonexistent")
        self.assertEqual(response.status_code, 400)

    def test_streams_chunk_events(self):
        key = self._setup_session()
        with patch("analyzer.views.get_service", return_value=FakeClaudeService("Hello")):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("event: chunk", content)
        self.assertIn("Hello", content)

    def test_sends_done_event_at_end(self):
        key = self._setup_session()
        with patch("analyzer.views.get_service", return_value=FakeClaudeService("text")):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            content = self._consume(response)
        self.assertTrue(content.endswith("event: done\ndata: \n\n"))

    def test_content_type_is_event_stream(self):
        key = self._setup_session()
        with patch("analyzer.views.get_service", return_value=FakeClaudeService("text")):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
        self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_session_key_consumed_after_stream(self):
        key = self._setup_session()
        with patch("analyzer.views.get_service", return_value=FakeClaudeService("text")):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            self._consume(response)
        self.assertNotIn(key, self.client.session)

    def test_renders_markdown_after_streaming(self):
        key = self._setup_session()
        with patch("analyzer.views.get_service", return_value=FakeClaudeService("## ATS Score\n80/100")):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("event: render", content)
        self.assertIn("<h2>ATS Score</h2>", content)

    def test_no_render_event_on_error(self):
        key = self._setup_session()
        fake = FakeClaudeService()
        fake.stream = MagicMock(side_effect=ClaudeServiceError("Rate limit hit.", 502))
        with patch("analyzer.views.get_service", return_value=fake):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            content = self._consume(response)
        self.assertNotIn("event: render", content)
        self.assertIn("event: done", content)

    def test_service_error_streamed_as_error_chunk(self):
        key = self._setup_session()
        fake = FakeClaudeService()
        fake.stream = MagicMock(side_effect=ClaudeServiceError("Rate limit hit.", 502))
        with patch("analyzer.views.get_service", return_value=fake):
            response = self.client.get(f"/analyzer/analyze/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("result-error", content)
        self.assertIn("Rate limit hit.", content)
        self.assertIn("event: done", content)
