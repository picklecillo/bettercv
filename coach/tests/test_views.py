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

    def _post_followup(self, fake, user_message="I led a team of 5.", exp_index="0"):
        _seed_coach_session(self.client)
        with patch("coach.views.get_coach_service", return_value=fake):
            return self.client.post("/coach/chat/", {
                "exp_index": exp_index,
                "user_message": user_message,
                "is_followup": "1",
            })

    def test_followup_returns_user_bubble_and_sse_container(self):
        response = self._post_followup(_fake())

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("I led a team of 5.", content)   # user bubble
        self.assertIn("sse-connect", content)           # SSE container

    def test_followup_empty_message_returns_error(self):
        response = self._post_followup(_fake(), user_message="  ")

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

    def test_followup_stream_includes_prior_history(self):
        """After a first turn, a second stream call should receive full history."""
        fake = _fake()

        # First turn
        nonce1 = self._setup_stream(fake)
        with patch("coach.views.get_coach_service", return_value=fake):
            self._consume(self.client.get(f"/coach/stream/?key={nonce1}"))

        # Second turn (follow-up)
        with patch("coach.views.get_coach_service", return_value=fake):
            self.client.post("/coach/chat/", {
                "exp_index": "0",
                "user_message": "Make it shorter.",
                "is_followup": "1",
            })
        # Find the new nonce in session
        nonce2 = next(
            k for k in self.client.session.keys()
            if k != "coach" and isinstance(self.client.session[k], dict)
            and "user_message" in self.client.session[k]
        )

        # Capture what history stream_reply receives
        received_history = []
        original_stream_reply = fake.stream_reply

        def capturing_stream_reply(work_experience, history):
            received_history.extend(history)
            yield from original_stream_reply(work_experience, history)

        fake.stream_reply = capturing_stream_reply
        with patch("coach.views.get_coach_service", return_value=fake):
            self._consume(self.client.get(f"/coach/stream/?key={nonce2}"))

        # Should contain the first turn's exchange plus new user message
        roles = [m["role"] for m in received_history]
        self.assertIn("user", roles)
        self.assertIn("assistant", roles)
        self.assertEqual(received_history[-1]["content"], "Make it shorter.")

    def test_wrap_event_contains_assistant_message(self):
        fake = _fake()
        nonce = self._setup_stream(fake)
        with patch("coach.views.get_coach_service", return_value=fake):
            response = self.client.get(f"/coach/stream/?key={nonce}")
            content = self._consume(response)
        self.assertIn("event: wrap", content)
        self.assertIn("assistant-msg", content)
        self.assertIn("msg-body", content)

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


class CoachConversationTests(TestCase):

    def _seed_with_history(self):
        _seed_coach_session(self.client)
        session = self.client.session
        session["coach"]["conversations"]["0"] = [
            {"role": "user", "content": "Built things."},
            {"role": "assistant", "content": "What were your biggest achievements?"},
        ]
        session.save()

    def test_returns_200_with_existing_history(self):
        self._seed_with_history()
        response = self.client.get("/coach/conversation/0/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("biggest achievements", response.content.decode())

    def test_returns_200_with_no_history(self):
        _seed_coach_session(self.client)
        response = self.client.get("/coach/conversation/0/")
        self.assertEqual(response.status_code, 200)

    def test_no_session_returns_error(self):
        response = self.client.get("/coach/conversation/0/")
        self.assertEqual(response.status_code, 400)


class ExperienceSwitchingTests(TestCase):

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def test_coaching_second_experience_does_not_affect_first(self):
        fake = _fake()
        _seed_coach_session(self.client)

        # Coach experience 0
        with patch("coach.views.get_coach_service", return_value=fake):
            r0 = self.client.post("/coach/chat/", {"exp_index": "0"})
        import re
        nonce0 = re.search(r'key=([\w-]+)', r0.content.decode()).group(1)
        with patch("coach.views.get_coach_service", return_value=fake):
            self._consume(self.client.get(f"/coach/stream/?key={nonce0}"))

        history_0_after_first = list(self.client.session["coach"]["conversations"]["0"])

        # Coach experience 1
        with patch("coach.views.get_coach_service", return_value=fake):
            r1 = self.client.post("/coach/chat/", {"exp_index": "1"})
        nonce1 = re.search(r'key=([\w-]+)', r1.content.decode()).group(1)
        with patch("coach.views.get_coach_service", return_value=fake):
            self._consume(self.client.get(f"/coach/stream/?key={nonce1}"))

        # Experience 0 history should be unchanged
        self.assertEqual(
            self.client.session["coach"]["conversations"]["0"],
            history_0_after_first,
        )
        # Experience 1 history should exist separately
        self.assertIn("1", self.client.session["coach"]["conversations"])


class CoachIndexTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/coach/")
        self.assertEqual(response.status_code, 200)

    def test_get_clears_existing_coach_session(self):
        _seed_coach_session(self.client)
        self.assertIn("coach", self.client.session)

        self.client.get("/coach/")

        self.assertNotIn("coach", self.client.session)


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

    def test_parse_records_shared_resume_version(self):
        session = self.client.session
        session["shared_resume"] = {"resume_text": "r", "resume_filename": None, "version": 3}
        session.save()
        self._post_text(_fake())
        self.assertEqual(self.client.session["coach"]["resume_version"], 3)

    def test_parse_preserves_existing_conversations(self):
        _seed_coach_session(self.client)
        session = self.client.session
        session["coach"]["conversations"]["0"] = [{"role": "user", "content": "hello"}]
        session.save()
        self._post_text(_fake())
        self.assertEqual(
            self.client.session["coach"]["conversations"]["0"],
            [{"role": "user", "content": "hello"}],
        )


class CoachWorkspaceTests(TestCase):

    def test_redirects_to_index_when_no_session(self):
        response = self.client.get("/coach/workspace/")
        self.assertRedirects(response, "/coach/", fetch_redirect_response=False)

    def test_returns_200_with_session(self):
        _seed_coach_session(self.client)
        response = self.client.get("/coach/workspace/")
        self.assertEqual(response.status_code, 200)

    def test_stale_banner_present_when_version_mismatch(self):
        _seed_coach_session(self.client)
        session = self.client.session
        session["shared_resume"] = {"resume_text": "new", "resume_filename": None, "version": 2}
        session["coach"]["resume_version"] = 1
        session.save()
        response = self.client.get("/coach/workspace/")
        self.assertContains(response, "resume has changed")

    def test_stale_banner_absent_when_versions_match(self):
        _seed_coach_session(self.client)
        session = self.client.session
        session["shared_resume"] = {"resume_text": "r", "resume_filename": None, "version": 1}
        session["coach"]["resume_version"] = 1
        session.save()
        response = self.client.get("/coach/workspace/")
        self.assertNotContains(response, "resume has changed")
