import logging
import pathlib
import subprocess
import tempfile

logger = logging.getLogger(__name__)


class RenderCVBuildError(Exception):
    pass


class RenderCVBuilder:
    def build_pdf(self, yaml_content: str, session_key: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)
            yaml_filename = f"resume_{session_key}.yaml"
            (tmppath / yaml_filename).write_text(yaml_content, encoding="utf-8")
            pdf_path = tmppath / "out.pdf"

            result = subprocess.run(
                [
                    "rendercv", "render", yaml_filename,
                    "--pdf-path", "out.pdf",
                    "--dont-generate-markdown",
                    "--dont-generate-png",
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )
            if result.returncode != 0:
                detail = (result.stderr.strip() or result.stdout.strip() or "rendercv failed")
                logger.error("rendercv failed (rc=%d):\nSTDOUT:\n%s\nSTDERR:\n%s\nYAML:\n%s",
                             result.returncode, result.stdout, result.stderr, yaml_content)
                raise RenderCVBuildError(detail)

            if not pdf_path.exists():
                raise RenderCVBuildError("PDF was not produced.")
            return pdf_path.read_bytes()

    def render_html(self, yaml_content: str, session_key: str) -> str:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = pathlib.Path(tmpdir)
            yaml_filename = f"resume_{session_key}.yaml"
            (tmppath / yaml_filename).write_text(yaml_content, encoding="utf-8")
            html_path = tmppath / "out.html"

            result = subprocess.run(
                [
                    "rendercv", "render", yaml_filename,
                    "--html-path", "out.html",
                    "--dont-generate-typst",
                    "--dont-generate-pdf",
                    "--dont-generate-png",
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )
            if result.returncode != 0:
                detail = (result.stderr.strip() or result.stdout.strip() or "rendercv failed")
                logger.error("rendercv failed (rc=%d):\nSTDOUT:\n%s\nSTDERR:\n%s\nYAML:\n%s",
                             result.returncode, result.stdout, result.stderr, yaml_content)
                raise RenderCVBuildError(detail)

            if not html_path.exists():
                raise RenderCVBuildError("HTML was not produced.")
            return html_path.read_text(encoding="utf-8")


def get_builder() -> RenderCVBuilder:
    return RenderCVBuilder()
