from unittest.mock import MagicMock
from django.test import TestCase
import anthropic

from coach.coach_service import CoachParseError, CoachService, WorkExperience


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
