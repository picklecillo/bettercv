import io

from ruamel.yaml import YAML


class ExperienceNotFoundError(Exception):
    pass


def _parse_rewrite(rewrite_text: str) -> tuple[str | None, list[str]]:
    summary_lines: list[str] = []
    highlights: list[str] = []
    for line in rewrite_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        is_bullet = False
        for prefix in ("-", "•", "*"):
            if stripped.startswith(prefix):
                content = stripped[len(prefix):].strip()
                if content:
                    highlights.append(content)
                is_bullet = True
                break
        if not is_bullet:
            summary_lines.append(stripped)
    summary = " ".join(summary_lines) if summary_lines else None
    return summary, highlights


def apply_experience_rewrite(yaml_str: str, company: str, position: str, rewrite_text: str) -> str:
    """
    Find the experience entry matching company+position (case-insensitive), replace
    its summary and highlights with content parsed from rewrite_text, and return updated YAML.

    Raises ExperienceNotFoundError if no matching entry is found.
    """
    ryaml = YAML()
    ryaml.preserve_quotes = True
    data = ryaml.load(yaml_str)

    experiences = (data or {}).get("cv", {}).get("sections", {}).get("experience", []) or []

    company_key = company.strip().lower()
    position_key = position.strip().lower()

    match = None
    for entry in experiences:
        if not isinstance(entry, dict):
            continue
        if (
            entry.get("company", "").strip().lower() == company_key
            and entry.get("position", "").strip().lower() == position_key
        ):
            match = entry
            break

    if match is None:
        raise ExperienceNotFoundError(f"No experience entry found for '{company}' / '{position}'")

    summary, highlights = _parse_rewrite(rewrite_text)
    if summary:
        match["summary"] = summary
    elif "summary" in match:
        del match["summary"]
    match["highlights"] = highlights

    buf = io.StringIO()
    ryaml.dump(data, buf)
    return buf.getvalue()


# Backward-compatible alias
apply_experience_highlights = apply_experience_rewrite
