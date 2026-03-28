from unittest.mock import MagicMock
from django.test import TestCase
import anthropic

from coach.coach_service import CoachParseError, CoachService, WorkExperience

_EXPERIENCE = WorkExperience(
    company="Acme Corp",
    title="Senior Engineer",
    dates="Jan 2019 – Mar 2022",
    original_description="Maintained legacy systems.",
)


def _make_streaming_client(chunks: list[str]) -> MagicMock:
    fake_stream = MagicMock()
    fake_stream.__enter__ = lambda s: s
    fake_stream.__exit__ = MagicMock(return_value=False)
    fake_stream.text_stream = iter(chunks)
    client = MagicMock(spec=anthropic.Anthropic)
    client.messages.stream.return_value = fake_stream
    return client


def _make_tool_use_response(experiences: list[dict]):
    """Build a minimal Anthropic response containing a tool_use block."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.input = {"experiences": experiences}

    response = MagicMock()
    response.content = [tool_use_block]
    return response


class CoachServiceParseTests(TestCase):

    def _make_service(self, api_response):
        client = MagicMock(spec=anthropic.Anthropic)
        client.messages.create.return_value = api_response
        return CoachService(client)

    def test_valid_cv_returns_work_experiences(self):
        raw = [
            {
                "company": "Acme Corp",
                "title": "Senior Engineer",
                "dates": "Jan 2019 – Mar 2022",
                "original_description": "Built things.",
            }
        ]
        service = self._make_service(_make_tool_use_response(raw))

        result = service.parse_cv("some cv text")

        self.assertEqual(len(result), 1)
        exp = result[0]
        self.assertIsInstance(exp, WorkExperience)
        self.assertEqual(exp.company, "Acme Corp")
        self.assertEqual(exp.title, "Senior Engineer")
        self.assertEqual(exp.dates, "Jan 2019 – Mar 2022")
        self.assertEqual(exp.original_description, "Built things.")

    def test_missing_tool_use_block_raises_parse_error(self):
        response = MagicMock()
        response.content = []  # no tool_use block
        service = self._make_service(response)

        with self.assertRaises(CoachParseError):
            service.parse_cv("some cv text")

    def test_empty_experiences_array_raises_parse_error(self):
        service = self._make_service(_make_tool_use_response([]))

        with self.assertRaises(CoachParseError):
            service.parse_cv("some cv text")


class CoachServiceStreamReplyTests(TestCase):

    def test_stream_reply_yields_chunks(self):
        client = _make_streaming_client(["Tell me ", "about your ", "achievements."])
        service = CoachService(client)

        result = "".join(service.stream_reply(_EXPERIENCE, []))

        self.assertEqual(result, "Tell me about your achievements.")

    def test_stream_reply_includes_work_experience_in_system_prompt(self):
        client = _make_streaming_client(["ok"])
        service = CoachService(client)

        list(service.stream_reply(_EXPERIENCE, []))  # consume to trigger API call

        call_kwargs = client.messages.stream.call_args.kwargs
        self.assertIn("Acme Corp", call_kwargs["system"])
        self.assertIn("Senior Engineer", call_kwargs["system"])
        self.assertIn("Maintained legacy systems.", call_kwargs["system"])

    def test_stream_reply_passes_history_as_messages(self):
        client = _make_streaming_client(["ok"])
        service = CoachService(client)
        history = [
            {"role": "user", "content": "Here is my experience."},
            {"role": "assistant", "content": "What did you achieve?"},
        ]

        list(service.stream_reply(_EXPERIENCE, history))  # consume to trigger API call

        call_kwargs = client.messages.stream.call_args.kwargs
        self.assertEqual(call_kwargs["messages"], history)
