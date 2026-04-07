import io
import uuid
from unittest.mock import patch

from django.test import TestCase

import apps.writer.views as writer_views
from apps.accounts.credits import credit_balance, grant_credits
from apps.shared.test_utils import AuthenticatedMixin, ZeroCreditsMixin


def _seed_shared_resume(client, resume_text="My resume.", filename=None, version=1):
    session = client.session
    session["shared_resume"] = {
        "resume_text": resume_text,
        "resume_filename": filename,
        "version": version,
    }
    session.save()


class IndexViewTests(AuthenticatedMixin, TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/writer/")
        self.assertEqual(response.status_code, 200)

    def test_get_shows_resume_textarea_and_pdf_upload(self):
        response = self.client.get("/writer/")
        self.assertContains(response, 'name="resume_text"')
        self.assertContains(response, 'name="resume_pdf"')

    def test_get_prefills_resume_from_session(self):
        _seed_shared_resume(self.client, resume_text="Experienced engineer")
        response = self.client.get("/writer/")
        self.assertContains(response, "Experienced engineer")

    def test_get_shows_filename_when_present(self):
        _seed_shared_resume(self.client, filename="my_cv.pdf")
        response = self.client.get("/writer/")
        self.assertContains(response, "my_cv.pdf")

    def test_get_no_filename_display_when_absent(self):
        _seed_shared_resume(self.client, filename=None)
        response = self.client.get("/writer/")
        self.assertNotContains(response, "Loaded from")

    def test_get_empty_form_when_no_session(self):
        response = self.client.get("/writer/")
        self.assertNotContains(response, "Loaded from")


class ParseViewTests(TestCase):

    def test_get_not_allowed(self):
        response = self.client.get("/writer/parse/")
        self.assertEqual(response.status_code, 405)

    def test_empty_text_returns_error(self):
        response = self.client.post("/writer/parse/", {"resume_text": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)

    def test_valid_text_stores_nonce_and_returns_sse_container(self):
        response = self.client.post("/writer/parse/", {"resume_text": "My resume"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"sse-connect", response.content)
        self.assertIn(b"/writer/stream/", response.content)

    def test_valid_text_stores_resume_in_session(self):
        self.client.post("/writer/parse/", {"resume_text": "My resume"})
        nonce_data = [
            v for k, v in self.client.session.items()
            if isinstance(v, dict) and "resume_text" in v
        ]
        self.assertEqual(len(nonce_data), 1)
        self.assertEqual(nonce_data[0]["resume_text"], "My resume")

    def test_pdf_upload_takes_priority_over_text(self):
        fake_pdf = io.BytesIO(b"fake pdf")
        fake_pdf.name = "cv.pdf"
        with patch("apps.writer.views.extract_text_from_pdf", return_value="PDF TEXT") as mock_pdf:
            response = self.client.post("/writer/parse/", {
                "resume_text": "pasted text",
                "resume_pdf": fake_pdf,
            })
        mock_pdf.assert_called_once()
        self.assertEqual(response.status_code, 200)
        nonce_data = [
            v for k, v in self.client.session.items()
            if isinstance(v, dict) and "resume_text" in v
        ]
        self.assertEqual(nonce_data[0]["resume_text"], "PDF TEXT")

    def test_unreadable_pdf_returns_error(self):
        from apps.shared.pdf import PdfExtractionError
        fake_pdf = io.BytesIO(b"bad pdf")
        fake_pdf.name = "cv.pdf"
        with patch("apps.writer.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Could not read the PDF file")):
            response = self.client.post("/writer/parse/", {"resume_pdf": fake_pdf})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)


class StreamViewTests(AuthenticatedMixin, TestCase):

    def _setup_session(self, resume_text="My resume"):
        key = str(uuid.uuid4())
        session = self.client.session
        session[key] = {"resume_text": resume_text}
        session.save()
        return key

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def test_missing_key_returns_400(self):
        response = self.client.get("/writer/stream/")
        self.assertEqual(response.status_code, 400)

    def test_unknown_key_returns_400(self):
        response = self.client.get("/writer/stream/?key=nonexistent")
        self.assertEqual(response.status_code, 400)

    def test_content_type_is_event_stream(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.return_value = iter(["full_name: John\n"])
            response = self.client.get(f"/writer/stream/?key={key}")
        self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_streams_chunk_events(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.return_value = iter(["full_name: John\n"])
            response = self.client.get(f"/writer/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("event: chunk", content)
        self.assertIn("full_name: John", content)

    def test_sends_done_event_at_end(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.return_value = iter(["text"])
            response = self.client.get(f"/writer/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("event: done", content)

    def test_session_key_consumed_after_stream(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.return_value = iter(["text"])
            response = self.client.get(f"/writer/stream/?key={key}")
            self._consume(response)
        self.assertNotIn(key, self.client.session)

    def test_service_error_sends_error_event_then_done(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.side_effect = Exception("API failure")
            response = self.client.get(f"/writer/stream/?key={key}")
            content = self._consume(response)
        self.assertIn("event: error", content)
        self.assertIn("API failure", content)
        self.assertIn("event: done", content)


class BuildViewTests(TestCase):

    def test_get_not_allowed(self):
        response = self.client.get("/writer/build/")
        self.assertEqual(response.status_code, 405)

    def test_empty_yaml_returns_error(self):
        response = self.client.post("/writer/build/", {"yaml_content": ""})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)

    def test_valid_yaml_returns_pdf(self):
        from apps.writer.tests.fakes import FakeRenderCVBuilder
        with patch("apps.writer.views.get_builder", return_value=FakeRenderCVBuilder()):
            response = self.client.post("/writer/build/", {
                "yaml_content": "cv:\n  name: John\n",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn("resume.pdf", response["Content-Disposition"])

    def test_build_error_returns_422(self):
        from apps.writer.rendercv_builder import RenderCVBuildError
        from apps.writer.tests.fakes import FakeRenderCVBuilder
        fake = FakeRenderCVBuilder()
        fake.should_raise = RenderCVBuildError("Invalid YAML structure")
        with patch("apps.writer.views.get_builder", return_value=fake):
            response = self.client.post("/writer/build/", {
                "yaml_content": "bad: yaml: content",
            })
        self.assertEqual(response.status_code, 422)
        self.assertIn(b"result-error", response.content)
        self.assertIn(b"Invalid YAML structure", response.content)


class RenderPreviewViewTests(TestCase):

    def test_get_not_allowed(self):
        response = self.client.get("/writer/render/")
        self.assertEqual(response.status_code, 405)

    def test_empty_yaml_returns_400(self):
        response = self.client.post("/writer/render/", {"yaml_content": ""})
        self.assertEqual(response.status_code, 400)

    def test_valid_yaml_returns_html_json(self):
        from apps.writer.tests.fakes import FAKE_HTML, FakeRenderCVBuilder
        with patch("apps.writer.views.get_builder", return_value=FakeRenderCVBuilder()):
            response = self.client.post("/writer/render/", {
                "yaml_content": "cv:\n  name: John\n",
            })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = response.json()
        self.assertIn("html", data)
        self.assertEqual(data["html"], FAKE_HTML)

    def test_render_error_returns_422_json(self):
        from apps.writer.rendercv_builder import RenderCVBuildError
        from apps.writer.tests.fakes import FakeRenderCVBuilder
        fake = FakeRenderCVBuilder()
        fake.should_raise = RenderCVBuildError("Bad YAML")
        with patch("apps.writer.views.get_builder", return_value=fake):
            response = self.client.post("/writer/render/", {
                "yaml_content": "bad: yaml",
            })
        self.assertEqual(response.status_code, 422)
        data = response.json()
        self.assertIn("error", data)
        self.assertIn("Bad YAML", data["error"])


class StreamCreditDeclarationTests(TestCase):

    def test_declared_stream_cost_is_one_credit(self):
        self.assertEqual(writer_views.STREAM_COST.amount, 1)

    def test_declared_description(self):
        self.assertEqual(writer_views.STREAM_COST.description, 'Resume Writer — YAML generation')


class StreamCreditSuccessTests(AuthenticatedMixin, TestCase):

    def _setup_session(self):
        key = str(uuid.uuid4())
        session = self.client.session
        session[key] = {"resume_text": "My resume"}
        session.save()
        return key

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def test_successful_stream_deducts_one_credit(self):
        grant_credits(self.user, 5, 'test')
        before = credit_balance(self.user)
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock:
            mock.return_value.stream_yaml.return_value = iter(["cv: {}\n"])
            self._consume(self.client.get(f"/writer/stream/?key={key}"))
        self.assertEqual(before - credit_balance(self.user), writer_views.STREAM_COST.amount)


class StreamZeroCreditsTests(ZeroCreditsMixin, TestCase):

    def _setup_session(self):
        key = str(uuid.uuid4())
        session = self.client.session
        session[key] = {"resume_text": "r"}
        session.save()
        return key

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def test_zero_credits_returns_sse_error(self):
        key = self._setup_session()
        content = self._consume(self.client.get(f"/writer/stream/?key={key}"))
        self.assertIn("credits-error", content)
        self.assertIn("event: done", content)

    def test_zero_credits_does_not_call_writer_service(self):
        key = self._setup_session()
        with patch("apps.writer.views.get_writer_service") as mock_svc:
            self._consume(self.client.get(f"/writer/stream/?key={key}"))
        mock_svc.assert_not_called()
