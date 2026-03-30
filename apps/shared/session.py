def get_shared_resume(session) -> dict | None:
    return session.get("shared_resume")


def set_shared_resume(session, text: str, filename: str | None = None) -> None:
    current = session.get("shared_resume") or {}
    version = current.get("version", 0) + 1
    session["shared_resume"] = {
        "resume_text": text,
        "resume_filename": filename,
        "version": version,
    }


def get_resume_version(session) -> int | None:
    shared = session.get("shared_resume")
    return shared["version"] if shared else None


def get_shared_yaml(session) -> str | None:
    return session.get("shared_yaml")


def set_shared_yaml(session, yaml_str: str) -> None:
    session["shared_yaml"] = yaml_str


def get_shared_html(session) -> str | None:
    return session.get("shared_html")


def set_shared_html(session, html_str: str) -> None:
    session["shared_html"] = html_str


def clear_shared_resume(session) -> None:
    session.pop("shared_resume", None)
    session.pop("shared_yaml", None)
    session.pop("shared_html", None)


def panel_context(session) -> dict:
    """Return the context dict needed by the shared resume panel in base.html."""
    return {
        "shared_resume": get_shared_resume(session),
        "shared_yaml": get_shared_yaml(session),
        "shared_html": get_shared_html(session),
    }
