import uuid


def _mark_modified(session: dict) -> None:
    """Mark session as modified for nested-dict mutations Django can't detect."""
    if hasattr(session, "modified"):
        session.modified = True


class SharedStore:
    def __init__(self, session: dict) -> None:
        self._s = session

    @property
    def resume(self) -> dict | None:
        """Full raw resume dict (text, filename, version) — for template context."""
        return self._s.get("shared_resume")

    @property
    def resume_text(self) -> str | None:
        r = self._s.get("shared_resume")
        return r["resume_text"] if r else None

    @property
    def resume_version(self) -> int | None:
        r = self._s.get("shared_resume")
        return r["version"] if r else None

    def set_resume(self, text: str, filename: str | None = None) -> None:
        current = self._s.get("shared_resume") or {}
        version = current.get("version", 0) + 1
        self._s["shared_resume"] = {
            "resume_text": text,
            "resume_filename": filename,
            "version": version,
        }

    @property
    def yaml(self) -> str | None:
        return self._s.get("shared_yaml")

    def bump_resume_version(self) -> None:
        """Increment resume version without changing text — signals resume content has changed."""
        current = self._s.get("shared_resume")
        if current:
            current["version"] = current.get("version", 0) + 1
            _mark_modified(self._s)

    def set_yaml(self, yaml_str: str) -> None:
        self._s["shared_yaml"] = yaml_str

    def invalidate_html(self) -> None:
        self._s.pop("shared_html", None)

    @property
    def html(self) -> str | None:
        return self._s.get("shared_html")

    def set_html(self, html_str: str) -> None:
        self._s["shared_html"] = html_str

    def panel_context(self) -> dict:
        return {
            "shared_resume": self._s.get("shared_resume"),
            "shared_yaml": self._s.get("shared_yaml"),
            "shared_html": self._s.get("shared_html"),
        }


class CoachStore:
    def __init__(self, session: dict) -> None:
        self._s = session

    @property
    def exists(self) -> bool:
        coach = self._s.get("coach")
        return bool(coach and coach.get("experiences"))

    def is_stale(self, shared: SharedStore) -> bool:
        shared_version = shared.resume_version
        if shared_version is None:
            return False
        coach = self._s.get("coach") or {}
        tool_version = coach.get("resume_version")
        if tool_version is None:
            return False
        return shared_version > tool_version

    @property
    def experiences(self) -> list[dict]:
        coach = self._s.get("coach") or {}
        return coach.get("experiences", [])

    @property
    def cv_text(self) -> str:
        coach = self._s.get("coach") or {}
        return coach.get("cv_text", "")

    @property
    def conversations(self) -> dict:
        coach = self._s.get("coach") or {}
        return coach.get("conversations", {})

    def initialize(
        self,
        cv_text: str,
        experiences: list[dict],
        resume_version: int | None,
        *,
        preserve_conversations: bool = True,
    ) -> None:
        existing_conversations: dict = {}
        if preserve_conversations:
            existing_conversations = (self._s.get("coach") or {}).get("conversations", {})
        self._s["coach"] = {
            "cv_text": cv_text,
            "experiences": experiences,
            "conversations": existing_conversations,
            "resume_version": resume_version,
        }

    def get_conversation(self, exp_index: int) -> list[dict]:
        coach = self._s.get("coach") or {}
        return coach.get("conversations", {}).get(str(exp_index), [])

    def save_conversation(self, exp_index: int, messages: list[dict]) -> None:
        """Persist a conversation and flush the session (safe to call inside generators)."""
        coach = self._s.get("coach") or {}
        coach.setdefault("conversations", {})[str(exp_index)] = messages
        _mark_modified(self._s)
        if hasattr(self._s, "save"):
            self._s.save()


class CompareStore:
    def __init__(self, session: dict) -> None:
        self._s = session

    @property
    def is_initialized(self) -> bool:
        return "compare" in self._s

    @property
    def has_jds(self) -> bool:
        compare = self._s.get("compare")
        return bool(compare and compare.get("jds"))

    def is_stale(self, shared: SharedStore) -> bool:
        shared_version = shared.resume_version
        if shared_version is None:
            return False
        compare = self._s.get("compare") or {}
        tool_version = compare.get("resume_version")
        if tool_version is None:
            return False
        return shared_version > tool_version

    def initialize(self, resume_text: str, resume_version: int | None) -> None:
        self._s["compare"] = {
            "resume_text": resume_text,
            "jds": {},
            "resume_version": resume_version,
        }

    @property
    def resume_text(self) -> str:
        compare = self._s.get("compare") or {}
        return compare.get("resume_text", "")

    def jd_count(self) -> int:
        compare = self._s.get("compare") or {}
        return len(compare.get("jds", {}))

    def add_jd(self, jd_id: str, jd_text: str) -> None:
        compare = self._s.get("compare") or {}
        compare.setdefault("jds", {})[jd_id] = {
            "jd_text": jd_text,
            "analysis": None,
            "metadata": None,
        }
        _mark_modified(self._s)

    def get_jd(self, jd_id: str) -> dict | None:
        compare = self._s.get("compare") or {}
        return compare.get("jds", {}).get(jd_id)

    def set_jd_result(self, jd_id: str, analysis: str, metadata: dict | None) -> None:
        """Persist analysis + metadata and flush the session (safe to call inside generators)."""
        compare = self._s.get("compare") or {}
        jds = compare.get("jds", {})
        if jd_id in jds:
            jds[jd_id]["analysis"] = analysis
            jds[jd_id]["metadata"] = metadata
        _mark_modified(self._s)
        if hasattr(self._s, "save"):
            self._s.save()

    def update_resume(self, resume_text: str, resume_version: int | None) -> None:
        compare = self._s.get("compare") or {}
        compare["resume_text"] = resume_text
        compare["resume_version"] = resume_version
        _mark_modified(self._s)

    def all_jds(self) -> list[tuple[str, dict]]:
        compare = self._s.get("compare") or {}
        return list(compare.get("jds", {}).items())


class NonceStore:
    def __init__(self, session: dict) -> None:
        self._s = session

    def put(self, payload: dict) -> str:
        key = str(uuid.uuid4())
        self._s[key] = payload
        _mark_modified(self._s)
        return key

    def pop(self, key: str) -> dict | None:
        value = self._s.pop(key, None)
        if value is not None:
            _mark_modified(self._s)
        return value


def shared(session: dict) -> SharedStore:
    return SharedStore(session)


def coach(session: dict) -> CoachStore:
    return CoachStore(session)


def compare(session: dict) -> CompareStore:
    return CompareStore(session)


def nonce(session: dict) -> NonceStore:
    return NonceStore(session)
