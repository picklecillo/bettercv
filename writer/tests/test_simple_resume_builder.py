from unittest.mock import MagicMock, patch

from django.test import TestCase

from writer.simple_resume_builder import SimpleResumeBuildError, SimpleResumeBuilder


class SimpleResumeBuilderTests(TestCase):

    def _fake_result(self, pdf_bytes=b"%PDF fake", exists=True):
        result = MagicMock()
        result.exists = exists
        result.output_path = "/tmp/fake/output/resume_key.pdf"
        mock_path = MagicMock()
        mock_path.read_bytes.return_value = pdf_bytes
        return result, mock_path

    def test_build_pdf_returns_bytes_on_success(self):
        fake_result = MagicMock()
        fake_result.exists = True
        fake_result.output_path = "/tmp/fake/output/resume_key.pdf"

        with patch("writer.simple_resume_builder.generate") as mock_gen, \
             patch("pathlib.Path.read_bytes", return_value=b"%PDF stub"):
            mock_gen.return_value = {"pdf": fake_result}
            result = SimpleResumeBuilder().build_pdf("full_name: John\n", "testkey")

        self.assertEqual(result, b"%PDF stub")

    def test_build_pdf_raises_on_simple_resume_error(self):
        from simple_resume.core.exceptions import GenerationError
        with patch("writer.simple_resume_builder.generate",
                   side_effect=GenerationError("bad yaml")):
            with self.assertRaises(SimpleResumeBuildError) as ctx:
                SimpleResumeBuilder().build_pdf("bad: yaml", "key")
        self.assertIn("bad yaml", str(ctx.exception))

    def test_build_pdf_raises_when_pdf_not_produced(self):
        fake_result = MagicMock()
        fake_result.exists = False

        with patch("writer.simple_resume_builder.generate") as mock_gen:
            mock_gen.return_value = {"pdf": fake_result}
            with self.assertRaises(SimpleResumeBuildError) as ctx:
                SimpleResumeBuilder().build_pdf("full_name: John\n", "key")

        self.assertIn("not produced", str(ctx.exception))

    def test_build_pdf_raises_on_unexpected_error(self):
        with patch("writer.simple_resume_builder.generate",
                   side_effect=RuntimeError("disk full")):
            with self.assertRaises(SimpleResumeBuildError) as ctx:
                SimpleResumeBuilder().build_pdf("full_name: John\n", "key")
        self.assertIn("disk full", str(ctx.exception))
