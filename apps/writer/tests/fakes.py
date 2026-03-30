FAKE_PDF_BYTES = b"%PDF-1.4 fake pdf content for testing"
FAKE_HTML = "<html><body><h1>John Doe</h1></body></html>"


class FakeRenderCVBuilder:
    def __init__(self):
        self.should_raise = None

    def build_pdf(self, yaml_content: str, session_key: str) -> bytes:
        if self.should_raise:
            raise self.should_raise
        return FAKE_PDF_BYTES

    def render_html(self, yaml_content: str, session_key: str) -> str:
        if self.should_raise:
            raise self.should_raise
        return FAKE_HTML
