import pathlib
import tempfile

from simple_resume.core.exceptions import SimpleResumeError
from simple_resume.shell.generate.core import GenerateOptions, generate


class SimpleResumeBuildError(Exception):
    pass


class SimpleResumeBuilder:
    def build_pdf(self, yaml_content: str, session_key: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = pathlib.Path(tmpdir)
            input_dir = tmp / "input"
            input_dir.mkdir()

            yaml_path = input_dir / f"resume_{session_key}.yaml"
            yaml_path.write_text(yaml_content, encoding="utf-8")

            try:
                opts = GenerateOptions(formats=["pdf"])
                result = generate(yaml_path, opts)
            except SimpleResumeError as e:
                raise SimpleResumeBuildError(str(e)) from e
            except Exception as e:
                raise SimpleResumeBuildError(f"PDF generation failed: {e}") from e

            pdf_result = result.get("pdf")
            if pdf_result is None or not pdf_result.exists:
                raise SimpleResumeBuildError("PDF was not produced.")

            return pathlib.Path(pdf_result.output_path).read_bytes()


def get_builder() -> SimpleResumeBuilder:
    return SimpleResumeBuilder()
