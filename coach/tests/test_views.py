from unittest.mock import patch

from django.test import Client, TestCase

from coach.coach_service import CoachParseError
from coach.tests.fakes import FAKE_EXPERIENCES, FakeCoachService


def _fake(experiences=None, should_raise=None):
    return FakeCoachService(experiences=experiences, should_raise=should_raise)


class CoachIndexTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/coach/")
        self.assertEqual(response.status_code, 200)


class CoachParseTests(TestCase):

    def _post_text(self, fake, cv_text="My CV text"):
        with patch("coach.views.get_coach_service", return_value=fake):
            return self.client.post(
                "/coach/parse/",
                {"cv_text": cv_text},
            )

    def test_pasted_text_returns_200_with_experience_data(self):
        fake = _fake()
        response = self._post_text(fake)

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Acme Corp", content)
        self.assertIn("Senior Engineer", content)

    def _post_pdf(self, fake, pdf_content=b"pdf bytes", extra_post=None):
        from io import BytesIO
        from unittest.mock import patch as _patch
        pdf_file = BytesIO(pdf_content)
        pdf_file.name = "cv.pdf"
        post_data = {"resume_pdf": pdf_file}
        if extra_post:
            post_data.update(extra_post)
        with patch("coach.views.get_coach_service", return_value=fake):
            with _patch("coach.views.extract_text_from_pdf", return_value="Extracted CV text"):
                return self.client.post("/coach/parse/", post_data)

    def test_pdf_upload_returns_200_with_experience_data(self):
        fake = _fake()
        response = self._post_pdf(fake)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Acme Corp", response.content.decode())

    def test_pdf_takes_priority_over_pasted_text(self):
        fake = _fake()
        from io import BytesIO
        from unittest.mock import patch as _patch
        pdf_file = BytesIO(b"pdf bytes")
        pdf_file.name = "cv.pdf"
        with patch("coach.views.get_coach_service", return_value=fake):
            with _patch("coach.views.extract_text_from_pdf", return_value="PDF text") as mock_extract:
                self.client.post("/coach/parse/", {"resume_pdf": pdf_file, "cv_text": "Pasted text"})

        # parse_cv should have received the PDF-extracted text, not the pasted text
        self.assertEqual(fake.parse_cv_calls[0], "PDF text")

    def test_neither_input_returns_error(self):
        with patch("coach.views.get_coach_service", return_value=_fake()):
            response = self.client.post("/coach/parse/", {})

        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())

    def test_unreadable_pdf_returns_error(self):
        from io import BytesIO
        from unittest.mock import patch as _patch
        from analyzer.pdf import PdfExtractionError
        pdf_file = BytesIO(b"bad pdf")
        pdf_file.name = "cv.pdf"
        with _patch("coach.views.extract_text_from_pdf", side_effect=PdfExtractionError("Unreadable PDF.")):
            response = self.client.post("/coach/parse/", {"resume_pdf": pdf_file})

        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())

    def test_no_experiences_returns_error(self):
        fake = _fake(should_raise=CoachParseError("No work experiences found."))
        response = self._post_text(fake)

        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())

    def test_pasted_text_stores_cv_text_and_experiences_in_session(self):
        fake = _fake()
        self._post_text(fake, cv_text="My CV text")

        session = self.client.session
        coach_session = session["coach"]
        self.assertEqual(coach_session["cv_text"], "My CV text")
        self.assertEqual(len(coach_session["experiences"]), 2)
