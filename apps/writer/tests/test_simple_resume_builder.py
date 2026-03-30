from unittest.mock import MagicMock

from django.test import TestCase


class SimpleResumeBuilderTests(TestCase):

    def _fake_result(self, pdf_bytes=b"%PDF fake", exists=True):
        result = MagicMock()
        result.exists = exists
        result.output_path = "/tmp/fake/output/resume_key.pdf"
        mock_path = MagicMock()
        mock_path.read_bytes.return_value = pdf_bytes
        return result, mock_path

    def test_build_pdf_returns_bytes_on_success(self):
        pass

    def test_build_pdf_raises_on_simple_resume_error(self):
        pass

    def test_build_pdf_raises_when_pdf_not_produced(self):
        pass

    def test_build_pdf_raises_on_unexpected_error(self):
        pass
