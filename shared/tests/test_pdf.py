import io
from unittest.mock import MagicMock, patch

from django.test import TestCase

from shared.pdf import PdfExtractionError, extract_text_from_pdf


class ExtractTextFromPdfTests(TestCase):

    def test_extracts_text_from_pages(self):
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "Page one text"
        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("shared.pdf.pdfplumber.open", return_value=mock_pdf):
            result = extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertEqual(result, "Page one text")

    def test_skips_pages_with_no_text(self):
        page_with_text = MagicMock()
        page_with_text.extract_text.return_value = "Real content"
        page_empty = MagicMock()
        page_empty.extract_text.return_value = None
        mock_pdf = MagicMock()
        mock_pdf.pages = [page_empty, page_with_text]
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("shared.pdf.pdfplumber.open", return_value=mock_pdf):
            result = extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertEqual(result, "Real content")

    def test_raises_on_empty_pdf(self):
        mock_pdf = MagicMock()
        mock_pdf.pages = []
        mock_pdf.__enter__ = lambda s: s
        mock_pdf.__exit__ = MagicMock(return_value=False)

        with patch("shared.pdf.pdfplumber.open", return_value=mock_pdf):
            with self.assertRaises(PdfExtractionError) as ctx:
                extract_text_from_pdf(io.BytesIO(b"fake pdf"))

        self.assertIn("scanned", str(ctx.exception))

    def test_raises_on_unreadable_pdf(self):
        with patch("shared.pdf.pdfplumber.open", side_effect=Exception("corrupt")):
            with self.assertRaises(PdfExtractionError) as ctx:
                extract_text_from_pdf(io.BytesIO(b"bad pdf"))

        self.assertIn("Could not read", str(ctx.exception))
