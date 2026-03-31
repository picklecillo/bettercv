from django.test import TestCase

from apps.coach.yaml_utils import ExperienceNotFoundError, apply_experience_highlights

SAMPLE_YAML = """\
cv:
  name: Jane Smith
  sections:
    experience:
      - company: Acme Corp
        position: Senior Engineer
        start_date: '2021-01'
        end_date: present
        highlights:
          - Built core platform services.
          - Maintained CI/CD pipelines.
      - company: Startup Ltd
        position: Engineer
        start_date: '2018-06'
        end_date: '2020-12'
        highlights:
          - Worked on the product.
"""

REWRITE = "- Led a team of 5 engineers.\n- Reduced latency by 40%.\n- Mentored 2 junior devs."


class ApplyExperienceHighlightsTests(TestCase):

    def test_replaces_highlights_for_matching_experience(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE)

        from ruamel.yaml import YAML
        data = YAML().load(result)
        highlights = data["cv"]["sections"]["experience"][0]["highlights"]
        self.assertEqual(highlights, [
            "Led a team of 5 engineers.",
            "Reduced latency by 40%.",
            "Mentored 2 junior devs.",
        ])

    def test_does_not_modify_other_experience_entries(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE)

        from ruamel.yaml import YAML
        data = YAML().load(result)
        second = data["cv"]["sections"]["experience"][1]["highlights"]
        self.assertEqual(second, ["Worked on the product."])

    def test_matching_is_case_insensitive(self):
        result = apply_experience_highlights(SAMPLE_YAML, "acme corp", "senior engineer", REWRITE)

        from ruamel.yaml import YAML
        data = YAML().load(result)
        highlights = data["cv"]["sections"]["experience"][0]["highlights"]
        self.assertEqual(len(highlights), 3)

    def test_strips_dash_bullet_prefix(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "- Led team.\n- Cut costs.")

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_strips_bullet_character_prefix(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "• Led team.\n• Cut costs.")

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_strips_asterisk_prefix(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "* Led team.\n* Cut costs.")

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_handles_lines_without_prefix(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "Led team.\nCut costs.")

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_discards_blank_lines(self):
        result = apply_experience_highlights(
            SAMPLE_YAML, "Acme Corp", "Senior Engineer", "- Led team.\n\n\n- Cut costs."
        )

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_raises_when_company_not_found(self):
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_highlights(SAMPLE_YAML, "Unknown Corp", "Senior Engineer", REWRITE)

    def test_raises_when_position_not_found(self):
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Wrong Title", REWRITE)

    def test_raises_when_no_experience_section(self):
        yaml_no_exp = "cv:\n  name: Jane\n  sections:\n    summary:\n      - Summary here.\n"
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_highlights(yaml_no_exp, "Acme Corp", "Senior Engineer", REWRITE)

    def test_output_is_valid_yaml(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE)

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertIn("cv", data)

    def test_preserves_other_cv_fields(self):
        result = apply_experience_highlights(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE)

        from ruamel.yaml import YAML
        data = YAML().load(result)
        self.assertEqual(data["cv"]["name"], "Jane Smith")
