import dataclasses
from unittest.mock import patch

from django.test import Client, TestCase

from coach.coach_service import CoachParseError
from coach.tests.fakes import FAKE_EXPERIENCES, FakeCoachService


def _seed_coach_session(client):
    """Store parsed experiences in the session as the parse view would."""
    session = client.session
    session["coach"] = {
        "cv_text": "My full CV text.",
        "experiences": [dataclasses.asdict(e) for e in FAKE_EXPERIENCES],
        "conversations": {},
    }
    session.save()


def _fake(experiences=None, should_raise=None):
    return FakeCoachService(experiences=experiences, should_raise=should_raise)


class CoachChatTests(TestCase):

    def _post_chat(self, fake, exp_index="0"):
        _seed_coach_session(self.client)
        with patch("coach.views.get_coach_service", return_value=fake):
            return self.client.post("/coach/chat/", {"exp_index": exp_index})

    def test_valid_exp_index_returns_sse_container(self):
        response = self._post_chat(_fake())

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("sse-connect", content)
        self.assertIn("/coach/stream/", content)

    def test_no_coach_session_returns_error(self):
        with patch("coach.views.get_coach_service", return_value=_fake()):
            response = self.client.post("/coach/chat/", {"exp_index": "0"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())


class CoachStreamTests(TestCase):

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def _setup_stream(self, fake):
        """Seed session and do a chat POST to get a nonce, return the nonce."""
        _seed_coach_session(self.client)
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.post("/coach/chat/", {"exp_index": "0"})
        # Extract the nonce from the SSE container URL in the response
        import re
        match = re.search(r'/coach/stream/\?key=([\w-]+)', response.content.decode())
        return match.group(1)

    def test_missing_key_returns_400(self):
        response = self.client.get("/coach/stream/")
        self.assertEqual(response.status_code, 400)

    def test_unknown_key_returns_400(self):
        response = self.client.get("/coach/stream/?key=nonexistent")
        self.assertEqual(response.status_code, 400)

    def test_streams_chunk_events(self):
        fake = _fake()
        nonce = self._setup_stream(fake)
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.get(f"/coach/stream/?key={nonce}")
            content = self._consume(response)
        self.assertIn("event: chunk", content)
        self.assertIn("achievements", content)

    def test_sends_done_event_at_end(self):
        fake = _fake()
        nonce = self._setup_stream(fake)
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.get(f"/coach/stream/?key={nonce}")
            content = self._consume(response)
        self.assertTrue(content.endswith("event: done\ndata: \n\n"))

    def test_exchange_committed_to_session_history_after_stream(self):
        fake = _fake()
        nonce = self._setup_stream(fake)
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.get(f"/coach/stream/?key={nonce}")
            self._consume(response)
        history = self.client.session["coach"]["conversations"]["0"]
        self.assertEqual(history[-1]["role"], "assistant")
        self.assertIn("achievements", history[-1]["content"])

    def test_error_not_committed_to_history(self):
        from unittest.mock import MagicMock
        fake = _fake()
        fake.stream_reply = MagicMock(side_effect=Exception("API down"))
        nonce = self._setup_stream(_fake())  # use plain fake to get nonce
        # Now replace with error fake for the stream call
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.get(f"/coach/stream/?key={nonce}")
            self._consume(response)
        conversations = self.client.session["coach"]["conversations"]
        self.assertEqual(conversations, {})


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
