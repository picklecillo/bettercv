import io

from ruamel.yaml import YAML


class ExperienceNotFoundError(Exception):
    pass


def _parse_bullets(rewrite_text: str) -> list[str]:
    lines = []
    for line in rewrite_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for prefix in ("-", "•", "*"):
            if stripped.startswith(prefix):
                stripped = stripped[len(prefix) :].strip()
                break
        if stripped:
            lines.append(stripped)
    return lines


def apply_experience_highlights(yaml_str: str, company: str, position: str, rewrite_text: str) -> str:
    """
    Find the experience entry matching company+position (case-insensitive), replace
    its highlights list with bullets parsed from rewrite_text, and return updated YAML.

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

    match["highlights"] = _parse_bullets(rewrite_text)

    buf = io.StringIO()
    ryaml.dump(data, buf)
    return buf.getvalue()
