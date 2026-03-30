import io
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.shared.pdf import PdfExtractionError
from apps.writer.rendercv_builder import RenderCVBuildError


def _seed_shared_resume(client, resume_text="My resume.", filename=None, version=1):
    session = client.session
    session["shared_resume"] = {
        "resume_text": resume_text,
        "resume_filename": filename,
        "version": version,
    }
    session.save()


def _seed_shared_resume_with_preview(client, resume_text="My resume.", filename=None):
    session = client.session
    session["shared_resume"] = {
        "resume_text": resume_text,
        "resume_filename": filename,
        "version": 1,
    }
    session["shared_yaml"] = "cv:\n  name: Test"
    session["shared_html"] = "<html><body>Preview</body></html>"
    session.save()


def _mock_writer_and_builder(yaml="cv:\n  name: Test", html="<html><body>Preview</body></html>"):
    """Return context managers that patch writer service and rendercv builder."""
    fake_service = MagicMock()
    fake_service.stream_yaml.return_value = iter([yaml])

    fake_builder = MagicMock()
    fake_builder.render_html.return_value = html
    fake_builder.build_pdf.return_value = b"%PDF-fake"

    patch_service = patch("apps.home.views.get_writer_service", return_value=fake_service)
    patch_builder = patch("apps.home.views.get_builder", return_value=fake_builder)
    return patch_service, patch_builder


class LandingPageTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)

    def test_landing_contains_product_description(self):
        response = self.client.get("/")
        self.assertContains(response, "BetterCV")

    def test_landing_has_cta_link_to_home(self):
        response = self.client.get("/")
        self.assertContains(response, "/home/")


class HomeIndexTests(TestCase):

    def test_get_returns_200(self):
        response = self.client.get("/home/")
        self.assertEqual(response.status_code, 200)

    def test_get_shows_upload_panel_when_no_resume(self):
        response = self.client.get("/home/")
        self.assertContains(response, 'name="resume_text"')
        self.assertContains(response, 'name="resume_pdf"')

    def test_get_shows_tool_ctas(self):
        response = self.client.get("/home/")
        self.assertContains(response, "ATS Analyzer")
        self.assertContains(response, "Resume Coach")
        self.assertContains(response, "Multi-JD Compare")

    def test_get_shows_preview_panel_when_html_in_session(self):
        _seed_shared_resume_with_preview(self.client)
        response = self.client.get("/home/")
        self.assertContains(response, "Edit YAML")
        self.assertContains(response, "Download PDF")
        self.assertNotContains(response, 'name="resume_text"')

    def test_tool_cards_show_filename_when_pdf_was_uploaded(self):
        _seed_shared_resume_with_preview(self.client, filename="my_cv.pdf")
        response = self.client.get("/home/")
        # filename shows in preview state badge
        self.assertContains(response, "my_cv.pdf")


class SubmitResumeTests(TestCase):

    def test_post_get_not_allowed(self):
        response = self.client.get("/resume/")
        self.assertEqual(response.status_code, 405)

    def test_panel_pasted_text_stores_resume_in_session(self):
        p_svc, p_bld = _mock_writer_and_builder()
        with p_svc, p_bld:
            self.client.post("/resume/", {"resume_text": "My resume text.", "source": "panel"})
        shared = self.client.session.get("shared_resume")
        self.assertIsNotNone(shared)
        self.assertEqual(shared["resume_text"], "My resume text.")
        self.assertIsNone(shared["resume_filename"])

    def test_panel_submission_generates_yaml_and_html(self):
        p_svc, p_bld = _mock_writer_and_builder(yaml="cv:\n  name: Jane", html="<html>Jane</html>")
        with p_svc, p_bld:
            self.client.post("/resume/", {"resume_text": "My resume.", "source": "panel"})
        self.assertEqual(self.client.session.get("shared_yaml"), "cv:\n  name: Jane")
        self.assertEqual(self.client.session.get("shared_html"), "<html>Jane</html>")

    def test_panel_submission_returns_preview_panel(self):
        p_svc, p_bld = _mock_writer_and_builder()
        with p_svc, p_bld:
            response = self.client.post("/resume/", {"resume_text": "My resume.", "source": "panel"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit YAML")
        self.assertContains(response, "Download PDF")

    def test_panel_pdf_upload_stores_filename(self):
        pdf_file = io.BytesIO(b"pdf bytes")
        pdf_file.name = "cv.pdf"
        p_svc, p_bld = _mock_writer_and_builder()
        with patch("apps.home.views.extract_text_from_pdf", return_value="PDF text"), p_svc, p_bld:
            self.client.post("/resume/", {"resume_pdf": pdf_file, "source": "panel"})
        shared = self.client.session.get("shared_resume")
        self.assertEqual(shared["resume_filename"], "cv.pdf")

    def test_panel_empty_submission_returns_error(self):
        response = self.client.post("/resume/", {"source": "panel"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)

    def test_panel_unreadable_pdf_returns_error(self):
        pdf_file = io.BytesIO(b"bad pdf")
        pdf_file.name = "cv.pdf"
        with patch("apps.home.views.extract_text_from_pdf",
                   side_effect=PdfExtractionError("Unreadable PDF.")):
            response = self.client.post("/resume/", {"resume_pdf": pdf_file, "source": "panel"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)

    def test_panel_render_failure_returns_error(self):
        p_svc, p_bld = _mock_writer_and_builder()
        fake_builder = MagicMock()
        fake_builder.render_html.side_effect = RenderCVBuildError("Bad YAML")
        p_bld_err = patch("apps.home.views.get_builder", return_value=fake_builder)
        with p_svc, p_bld_err:
            response = self.client.post("/resume/", {"resume_text": "My resume.", "source": "panel"})
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)

    def test_version_increments_on_each_panel_submission(self):
        p_svc, p_bld = _mock_writer_and_builder()
        with p_svc, p_bld:
            self.client.post("/resume/", {"resume_text": "First.", "source": "panel"})
        self.assertEqual(self.client.session["shared_resume"]["version"], 1)
        p_svc2, p_bld2 = _mock_writer_and_builder()
        with p_svc2, p_bld2:
            self.client.post("/resume/", {"resume_text": "Second.", "source": "panel"})
        self.assertEqual(self.client.session["shared_resume"]["version"], 2)

    def test_legacy_source_returns_redirect_to_home(self):
        response = self.client.post("/resume/", {"resume_text": "My resume."})
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response["HX-Redirect"], "/home/")


class ShowResumeEditorTests(TestCase):

    def test_editor_returns_editor_panel_with_yaml(self):
        session = self.client.session
        session["shared_yaml"] = "cv:\n  name: Jane"
        session.save()
        response = self.client.get("/resume/editor/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "cv:\n  name: Jane")
        self.assertContains(response, "Preview")

    def test_editor_without_yaml_shows_error(self):
        response = self.client.get("/resume/editor/")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "result-error")


class RenderResumeHtmlTests(TestCase):

    def test_render_updates_session_and_returns_preview(self):
        fake_builder = MagicMock()
        fake_builder.render_html.return_value = "<html>Updated</html>"
        with patch("apps.home.views.get_builder", return_value=fake_builder):
            response = self.client.post("/resume/render/", {"yaml_content": "cv:\n  name: Jane"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Edit YAML")
        self.assertEqual(self.client.session.get("shared_yaml"), "cv:\n  name: Jane")
        self.assertEqual(self.client.session.get("shared_html"), "<html>Updated</html>")

    def test_render_returns_editor_with_error_on_rendercv_failure(self):
        fake_builder = MagicMock()
        fake_builder.render_html.side_effect = RenderCVBuildError("Bad YAML")
        with patch("apps.home.views.get_builder", return_value=fake_builder):
            response = self.client.post("/resume/render/", {"yaml_content": "bad yaml"})
        self.assertEqual(response.status_code, 422)
        self.assertContains(response, "result-error", status_code=422)

    def test_render_returns_error_when_no_yaml_submitted(self):
        response = self.client.post("/resume/render/")
        self.assertEqual(response.status_code, 400)
        self.assertContains(response, "result-error", status_code=400)


class BuildResumePdfTests(TestCase):

    def test_build_uses_session_yaml_when_no_form_content(self):
        session = self.client.session
        session["shared_yaml"] = "cv:\n  name: Test"
        session.save()

        fake_builder = MagicMock()
        fake_builder.build_pdf.return_value = b"%PDF-fake"
        with patch("apps.home.views.get_builder", return_value=fake_builder):
            response = self.client.post("/resume/build/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    def test_build_uses_submitted_yaml_content(self):
        fake_builder = MagicMock()
        fake_builder.build_pdf.return_value = b"%PDF-fake"
        with patch("apps.home.views.get_builder", return_value=fake_builder):
            response = self.client.post("/resume/build/", {"yaml_content": "cv:\n  name: Jane"})
        self.assertEqual(response.status_code, 200)
        fake_builder.build_pdf.assert_called_once()
        call_args = fake_builder.build_pdf.call_args[0]
        self.assertEqual(call_args[0], "cv:\n  name: Jane")

    def test_build_returns_400_when_no_yaml(self):
        response = self.client.post("/resume/build/")
        self.assertEqual(response.status_code, 400)

    def test_build_returns_422_on_rendercv_error(self):
        session = self.client.session
        session["shared_yaml"] = "cv:\n  name: Test"
        session.save()
        fake_builder = MagicMock()
        fake_builder.build_pdf.side_effect = RenderCVBuildError("Failed")
        with patch("apps.home.views.get_builder", return_value=fake_builder):
            response = self.client.post("/resume/build/")
        self.assertEqual(response.status_code, 422)
