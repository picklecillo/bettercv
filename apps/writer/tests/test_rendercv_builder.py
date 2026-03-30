import subprocess
from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.writer.rendercv_builder import RenderCVBuilder, RenderCVBuildError


def _make_completed_process(returncode=0, stderr=""):
    proc = MagicMock(spec=subprocess.CompletedProcess)
    proc.returncode = returncode
    proc.stderr = stderr
    return proc


class RenderCVBuilderBuildPdfTests(TestCase):

    def test_returns_bytes_on_success(self):
        builder = RenderCVBuilder()
        fake_pdf = b"%PDF-1.4 fake"
        with patch("apps.writer.rendercv_builder.subprocess.run", return_value=_make_completed_process()) as mock_run, \
             patch("apps.writer.rendercv_builder.pathlib.Path.exists", return_value=True), \
             patch("apps.writer.rendercv_builder.pathlib.Path.read_bytes", return_value=fake_pdf):
            result = builder.build_pdf("cv:\n  name: John\n", "sess123")
        self.assertEqual(result, fake_pdf)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("--pdf-path", cmd)
        self.assertIn("--dont-generate-markdown", cmd)
        self.assertIn("--dont-generate-png", cmd)

    def test_raises_on_nonzero_returncode(self):
        builder = RenderCVBuilder()
        with patch("apps.writer.rendercv_builder.subprocess.run",
                   return_value=_make_completed_process(returncode=1, stderr="validation error")):
            with self.assertRaises(RenderCVBuildError) as ctx:
                builder.build_pdf("bad yaml", "sess123")
        self.assertIn("validation error", str(ctx.exception))

    def test_raises_when_pdf_not_produced(self):
        builder = RenderCVBuilder()
        with patch("apps.writer.rendercv_builder.subprocess.run", return_value=_make_completed_process()), \
             patch("apps.writer.rendercv_builder.pathlib.Path.exists", return_value=False):
            with self.assertRaises(RenderCVBuildError) as ctx:
                builder.build_pdf("cv:\n  name: John\n", "sess123")
        self.assertIn("not produced", str(ctx.exception))


class RenderCVBuilderRenderHtmlTests(TestCase):

    def test_returns_html_string_on_success(self):
        builder = RenderCVBuilder()
        fake_html = "<html><body>John Doe</body></html>"
        with patch("apps.writer.rendercv_builder.subprocess.run", return_value=_make_completed_process()) as mock_run, \
             patch("apps.writer.rendercv_builder.pathlib.Path.exists", return_value=True), \
             patch("apps.writer.rendercv_builder.pathlib.Path.read_text", return_value=fake_html):
            result = builder.render_html("cv:\n  name: John\n", "sess123")
        self.assertEqual(result, fake_html)
        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        self.assertIn("--html-path", cmd)
        self.assertIn("--dont-generate-typst", cmd)
        self.assertIn("--dont-generate-pdf", cmd)
        self.assertIn("--dont-generate-png", cmd)

    def test_raises_on_nonzero_returncode(self):
        builder = RenderCVBuilder()
        with patch("apps.writer.rendercv_builder.subprocess.run",
                   return_value=_make_completed_process(returncode=1, stderr="parse error")):
            with self.assertRaises(RenderCVBuildError) as ctx:
                builder.render_html("bad yaml", "sess123")
        self.assertIn("parse error", str(ctx.exception))

    def test_raises_when_html_not_produced(self):
        builder = RenderCVBuilder()
        with patch("apps.writer.rendercv_builder.subprocess.run", return_value=_make_completed_process()), \
             patch("apps.writer.rendercv_builder.pathlib.Path.exists", return_value=False):
            with self.assertRaises(RenderCVBuildError) as ctx:
                builder.render_html("cv:\n  name: John\n", "sess123")
        self.assertIn("not produced", str(ctx.exception))
