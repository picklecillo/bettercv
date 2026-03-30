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
