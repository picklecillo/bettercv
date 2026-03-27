import pdfplumber


class PdfExtractionError(Exception):
    pass


def extract_text_from_pdf(file) -> str:
    try:
        with pdfplumber.open(file) as pdf:
            text = "\n".join(page.extract_text() for page in pdf.pages if page.extract_text())
    except PdfExtractionError:
        raise
    except Exception as e:
        raise PdfExtractionError(f"Could not read the PDF file: {e}") from e

    if not text:
        raise PdfExtractionError(
            "No text could be extracted from the PDF. "
            "It may be scanned or image-based. Try pasting the text instead."
        )

    return text
