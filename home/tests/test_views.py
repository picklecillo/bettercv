import io
from unittest.mock import patch

from django.test import TestCase

from shared.pdf import PdfExtractionError


def _seed_shared_resume(client, resume_text="My resume.", filename=None, version=1):
    session = client.session
    session["shared_resume"] = {
        "resume_text": resume_text,
        "resume_filename": filename,
        "version": version,
    }
    session.save()


class HomeIndexTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_get_shows_intake_form_when_no_session_resume(self):
        response = self.client.get("/")
        self.assertContains(response, 'name="resume_text"')
        self.assertContains(response, 'name="resume_pdf"')

    def test_get_shows_tool_cards_when_session_resume_present(self):
        _seed_shared_resume(self.client)
        response = self.client.get("/")
        self.assertContains(response, "ATS Analyzer")
        self.assertContains(response, "Resume Coach")
        self.assertContains(response, "Multi-JD Compare")
        self.assertNotContains(response, 'name="resume_text"')

    def test_get_with_change_param_shows_form_even_when_resume_loaded(self):
        _seed_shared_resume(self.client)
        response = self.client.get("/?change=1")
        self.assertContains(response, 'name="resume_text"')

    def test_tool_cards_show_filename_when_pdf_was_uploaded(self):
        _seed_shared_resume(self.client, filename="my_cv.pdf")
        response = self.client.get("/")
        self.assertContains(response, "my_cv.pdf")


class SubmitResumeTests(TestCase):

    def test_post_get_not_allowed(self):
        response = self.client.get("/resume/")
        self.assertEqual(response.status_code, 405)

    def test_pasted_text_stores_shared_resume_in_session(self):
        self.client.post("/resume/", {"resume_text": "My resume text.", "source": "home"})
        shared = self.client.session.get("shared_resume")
        self.assertIsNotNone(shared)
        self.assertEqual(shared["resume_text"], "My resume text.")
        self.assertIsNone(shared["resume_filename"])
        self.assertEqual(shared["version"], 1)

    def test_pasted_text_returns_tool_cards_fragment(self):
        response = self.client.post("/resume/", {"resume_text": "My resume.", "source": "home"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ATS Analyzer")
        self.assertContains(response, "Resume Coach")

    def test_pdf_upload_stores_text_and_filename_in_session(self):
        pdf_file = io.BytesIO(b"pdf bytes")
        pdf_file.name = "cv.pdf"
        with patch("home.views.extract_text_from_pdf", return_value="PDF resume text"):
            self.client.post("/resume/", {"resume_pdf": pdf_file, "source": "home"})
        shared = self.client.session.get("shared_resume")
        self.assertEqual(shared["resume_text"], "PDF resume text")
        self.assertEqual(shared["resume_filename"], "cv.pdf")

    def test_pdf_upload_returns_tool_cards_fragment(self):
        pdf_file = io.BytesIO(b"pdf bytes")
        pdf_file.name = "cv.pdf"
        with patch("home.views.extract_text_from_pdf", return_value="PDF resume text"):
            response = self.client.post("/resume/", {"resume_pdf": pdf_file, "source": "home"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ATS Analyzer")

    def test_empty_submission_returns_error(self):
        response = self.client.post("/resume/", {"source": "home"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)

    def test_unreadable_pdf_returns_error(self):
        pdf_file = io.BytesIO(b"bad pdf")
        pdf_file.name = "cv.pdf"
        with patch("home.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Unreadable PDF.")):
            response = self.client.post("/resume/", {"resume_pdf": pdf_file, "source": "home"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)

    def test_version_increments_on_each_submission(self):
        self.client.post("/resume/", {"resume_text": "First resume.", "source": "home"})
        self.assertEqual(self.client.session["shared_resume"]["version"], 1)
        self.client.post("/resume/", {"resume_text": "Second resume.", "source": "home"})
        self.assertEqual(self.client.session["shared_resume"]["version"], 2)

    def test_non_home_source_returns_redirect_header(self):
        response = self.client.post("/resume/", {"resume_text": "My resume."})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/")
