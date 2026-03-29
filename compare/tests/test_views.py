from io import BytesIO
from unittest.mock import patch

from django.test import TestCase


class CompareParseResumeTests(TestCase):

    def test_pasted_text_returns_200_with_workspace(self):
        response = self.client.post("/compare/parse-resume/", {"resume_text": "My resume"})
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"compare-workspace", response.content)

    def test_pasted_text_stores_resume_in_session(self):
        self.client.post("/compare/parse-resume/", {"resume_text": "My resume"})
        self.assertEqual(self.client.session["compare"]["resume_text"], "My resume")

    def test_pasted_text_initialises_empty_jds_in_session(self):
        self.client.post("/compare/parse-resume/", {"resume_text": "My resume"})
        self.assertEqual(self.client.session["compare"]["jds"], {})


    def _post_pdf(self, extra_post=None):
        pdf_file = BytesIO(b"pdf bytes")
        pdf_file.name = "resume.pdf"
        post_data = {"resume_pdf": pdf_file}
        if extra_post:
            post_data.update(extra_post)
        with patch("compare.views.extract_text_from_pdf", return_value="PDF resume text"):
            return self.client.post("/compare/parse-resume/", post_data)

    def test_pdf_upload_returns_200_with_workspace(self):
        response = self._post_pdf()
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"compare-workspace", response.content)

    def test_pdf_takes_priority_over_pasted_text(self):
        with patch("compare.views.extract_text_from_pdf", return_value="PDF text") as mock:
            pdf_file = BytesIO(b"pdf bytes")
            pdf_file.name = "resume.pdf"
            self.client.post("/compare/parse-resume/", {
                "resume_pdf": pdf_file,
                "resume_text": "Pasted text",
            })
        self.assertEqual(self.client.session["compare"]["resume_text"], "PDF text")

    def test_neither_input_returns_error(self):
        response = self.client.post("/compare/parse-resume/", {})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)

    def test_unreadable_pdf_returns_error(self):
        from analyzer.pdf import PdfExtractionError
        pdf_file = BytesIO(b"bad pdf")
        pdf_file.name = "resume.pdf"
        with patch("compare.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Unreadable PDF.")):
            response = self.client.post("/compare/parse-resume/", {"resume_pdf": pdf_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)


class CompareIndexTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/compare/")
        self.assertEqual(response.status_code, 200)

    def test_get_clears_existing_compare_session(self):
        session = self.client.session
        session["compare"] = {"resume_text": "old resume", "jds": {}}
        session.save()

        self.client.get("/compare/")

        self.assertNotIn("compare", self.client.session)
