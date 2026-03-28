from coach.coach_service import CoachParseError, CoachService, WorkExperience


FAKE_EXPERIENCES = [
    WorkExperience(
        company="Acme Corp",
        title="Senior Engineer",
        dates="Jan 2019 – Mar 2022",
        original_description="Built and maintained core platform services.",
    ),
    WorkExperience(
        company="Startup Ltd",
        title="Engineer",
        dates="Jun 2016 – Dec 2018",
        original_description="Worked on the product.",
    ),
]


class FakeCoachService(CoachService):
    """Test double — no Anthropic client needed."""

    def __init__(self, experiences=None, should_raise=None):
        self._experiences = experiences if experiences is not None else list(FAKE_EXPERIENCES)
        self._should_raise = should_raise
        self.parse_cv_calls: list[str] = []

    def parse_cv(self, cv_text: str) -> list[WorkExperience]:
        self.parse_cv_calls.append(cv_text)
        if self._should_raise:
            raise self._should_raise
        return self._experiences
