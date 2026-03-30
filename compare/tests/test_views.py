from io import BytesIO
from unittest.mock import patch

from django.test import TestCase

from compare.compare_service import CompareMetadataError
from compare.tests.fakes import FAKE_METADATA, FakeCompareService


def _seed_compare_session(client, resume_text="My full resume."):
    session = client.session
    session["compare"] = {"resume_text": resume_text, "jds": {}}
    session.save()


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
        from shared.pdf import PdfExtractionError
        pdf_file = BytesIO(b"bad pdf")
        pdf_file.name = "resume.pdf"
        with patch("compare.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Unreadable PDF.")):
            response = self.client.post("/compare/parse-resume/", {"resume_pdf": pdf_file})
        self.assertEqual(response.status_code, 400)
        self.assertIn(b"result-error", response.content)

    def test_parse_records_shared_resume_version(self):
        session = self.client.session
        session["shared_resume"] = {"resume_text": "r", "resume_filename": None, "version": 2}
        session.save()
        self.client.post("/compare/parse-resume/", {"resume_text": "My resume"})
        self.assertEqual(self.client.session["compare"]["resume_version"], 2)


class CompareWorkspaceTests(TestCase):

    def test_redirects_to_index_when_no_session(self):
        response = self.client.get("/compare/workspace/")
        self.assertRedirects(response, "/compare/", fetch_redirect_response=False)

    def test_returns_200_with_session(self):
        _seed_compare_session(self.client)
        response = self.client.get("/compare/workspace/")
        self.assertEqual(response.status_code, 200)

    def test_stale_banner_present_when_version_mismatch(self):
        _seed_compare_session(self.client)
        session = self.client.session
        session["shared_resume"] = {"resume_text": "new", "resume_filename": None, "version": 2}
        session["compare"]["resume_version"] = 1
        session.save()
        response = self.client.get("/compare/workspace/")
        self.assertContains(response, "resume has changed")

    def test_stale_banner_absent_when_versions_match(self):
        _seed_compare_session(self.client)
        session = self.client.session
        session["shared_resume"] = {"resume_text": "r", "resume_filename": None, "version": 1}
        session["compare"]["resume_version"] = 1
        session.save()
        response = self.client.get("/compare/workspace/")
        self.assertNotContains(response, "resume has changed")


class AddJdTests(TestCase):

    def _post_jd(self, fake, jd_text="We need a senior engineer."):
        _seed_compare_session(self.client)
        with patch("compare.views.get_compare_service", return_value=fake):
            return self.client.post("/compare/add-jd/", {"jd_text": jd_text})

    def test_returns_card_with_sse_container(self):
        response = self._post_jd(FakeCompareService())
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("sse-connect", content)
        self.assertIn("/compare/stream/", content)

    def test_returns_oob_summary_row(self):
        response = self._post_jd(FakeCompareService())
        content = response.content.decode()
        self.assertIn("hx-swap-oob", content)
        self.assertIn("summary-row-", content)

    def test_no_session_returns_error(self):
        with patch("compare.views.get_compare_service", return_value=FakeCompareService()):
            response = self.client.post("/compare/add-jd/", {"jd_text": "some job"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())

    def test_empty_jd_returns_error(self):
        _seed_compare_session(self.client)
        with patch("compare.views.get_compare_service", return_value=FakeCompareService()):
            response = self.client.post("/compare/add-jd/", {"jd_text": "  "})
        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())

    def test_max_10_jds_returns_error(self):
        session = self.client.session
        session["compare"] = {
            "resume_text": "My resume.",
            "jds": {str(i): {} for i in range(10)},
        }
        session.save()
        with patch("compare.views.get_compare_service", return_value=FakeCompareService()):
            response = self.client.post("/compare/add-jd/", {"jd_text": "one more job"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("result-error", response.content.decode())


class CompareStreamTests(TestCase):

    def _consume(self, response):
        return b"".join(response.streaming_content).decode()

    def _setup_stream(self, fake):
        _seed_compare_session(self.client)
        with patch("compare.views.get_compare_service", return_value=fake):
            r = self.client.post("/compare/add-jd/", {"jd_text": "We need an engineer."})
        import re
        nonce = re.search(r'/compare/stream/\?key=([\w-]+)', r.content.decode()).group(1)
        jd_id = re.search(r'id="card-([\w-]+)"', r.content.decode()).group(1)
        return nonce, jd_id

    def test_missing_key_returns_400(self):
        response = self.client.get("/compare/stream/")
        self.assertEqual(response.status_code, 400)

    def test_unknown_key_returns_400(self):
        response = self.client.get("/compare/stream/?key=nonexistent")
        self.assertEqual(response.status_code, 400)

    def test_streams_chunk_events(self):
        fake = FakeCompareService()
        nonce, _ = self._setup_stream(fake)
        with patch("compare.views.get_compare_service", return_value=fake):
            content = self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        self.assertIn("event: chunk", content)
        self.assertIn("Strong match", content)

    def test_sends_done_event(self):
        fake = FakeCompareService()
        nonce, _ = self._setup_stream(fake)
        with patch("compare.views.get_compare_service", return_value=fake):
            content = self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        self.assertTrue(content.endswith("event: done\ndata: \n\n"))

    def test_commits_analysis_and_metadata_to_session(self):
        fake = FakeCompareService()
        nonce, jd_id = self._setup_stream(fake)
        with patch("compare.views.get_compare_service", return_value=fake):
            self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        jd = self.client.session["compare"]["jds"][jd_id]
        self.assertIsNotNone(jd["analysis"])
        self.assertEqual(jd["metadata"]["company"], "Acme Corp")
        self.assertEqual(jd["metadata"]["score_low"], 70)

    def test_metadata_event_contains_score_and_label(self):
        fake = FakeCompareService()
        nonce, _ = self._setup_stream(fake)
        with patch("compare.views.get_compare_service", return_value=fake):
            content = self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        self.assertIn("event: metadata", content)
        self.assertIn("70", content)
        self.assertIn("Acme Corp", content)

    def test_metadata_failure_still_commits_analysis(self):
        fake = FakeCompareService(raise_metadata=CompareMetadataError("failed"))
        nonce, jd_id = self._setup_stream(fake)
        with patch("compare.views.get_compare_service", return_value=fake):
            self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        jd = self.client.session["compare"]["jds"][jd_id]
        self.assertIsNotNone(jd["analysis"])
        self.assertIsNone(jd["metadata"])

    def test_errored_stream_not_committed(self):
        from unittest.mock import MagicMock
        fake = FakeCompareService()
        fake.stream_analysis = MagicMock(side_effect=Exception("API down"))
        nonce, jd_id = self._setup_stream(FakeCompareService())
        with patch("compare.views.get_compare_service", return_value=fake):
            self._consume(self.client.get(f"/compare/stream/?key={nonce}"))
        jd = self.client.session["compare"]["jds"][jd_id]
        self.assertIsNone(jd["analysis"])


class RemoveJdTests(TestCase):

    def _seed_with_jd(self, jd_id="abc-123"):
        session = self.client.session
        session["compare"] = {
            "resume_text": "My resume.",
            "jds": {jd_id: {"jd_text": "Some job.", "analysis": None, "metadata": None}},
        }
        session.save()
        return jd_id

    def test_removes_jd_from_session(self):
        jd_id = self._seed_with_jd()
        self.client.post("/compare/remove-jd/", {"jd_id": jd_id})
        self.assertNotIn(jd_id, self.client.session["compare"]["jds"])

    def test_returns_200_with_card_oob_delete(self):
        jd_id = self._seed_with_jd()
        response = self.client.post("/compare/remove-jd/", {"jd_id": jd_id})
        self.assertEqual(response.status_code, 200)
        self.assertIn(f'id="card-{jd_id}"', response.content.decode())
        self.assertIn('hx-swap-oob="delete"', response.content.decode())

    def test_no_session_returns_400(self):
        response = self.client.post("/compare/remove-jd/", {"jd_id": "x"})
        self.assertEqual(response.status_code, 400)

    def test_unknown_jd_id_returns_400(self):
        self._seed_with_jd("real-id")
        response = self.client.post("/compare/remove-jd/", {"jd_id": "fake-id"})
        self.assertEqual(response.status_code, 400)


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
