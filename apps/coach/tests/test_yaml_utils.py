from django.test import TestCase

from apps.coach.yaml_utils import ExperienceNotFoundError, apply_experience_rewrite

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

REWRITE_BULLETS_ONLY = "- Led a team of 5 engineers.\n- Reduced latency by 40%.\n- Mentored 2 junior devs."
REWRITE_WITH_SUMMARY = (
    "Drove platform reliability and team growth across a high-traffic production environment.\n\n"
    "- Led a team of 5 engineers.\n- Reduced latency by 40%.\n- Mentored 2 junior devs."
)


class ApplyExperienceRewriteTests(TestCase):

    def _load(self, yaml_str):
        from ruamel.yaml import YAML
        return YAML().load(yaml_str)

    # --- highlights ---

    def test_replaces_highlights_for_matching_experience(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], [
            "Led a team of 5 engineers.",
            "Reduced latency by 40%.",
            "Mentored 2 junior devs.",
        ])

    def test_does_not_modify_other_experience_entries(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][1]["highlights"], ["Worked on the product."])

    def test_matching_is_case_insensitive(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "acme corp", "senior engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        self.assertEqual(len(data["cv"]["sections"]["experience"][0]["highlights"]), 3)

    def test_strips_dash_bullet_prefix(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "- Led team.\n- Cut costs.")
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_strips_bullet_character_prefix(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "• Led team.\n• Cut costs.")
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_strips_asterisk_prefix(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", "* Led team.\n* Cut costs.")
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    def test_discards_blank_lines_between_bullets(self):
        result = apply_experience_rewrite(
            SAMPLE_YAML, "Acme Corp", "Senior Engineer", "- Led team.\n\n\n- Cut costs."
        )
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["highlights"], ["Led team.", "Cut costs."])

    # --- summary ---

    def test_sets_summary_when_paragraph_present(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_WITH_SUMMARY)
        data = self._load(result)
        exp = data["cv"]["sections"]["experience"][0]
        self.assertEqual(
            exp["summary"],
            "Drove platform reliability and team growth across a high-traffic production environment.",
        )

    def test_summary_and_highlights_both_set(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_WITH_SUMMARY)
        data = self._load(result)
        exp = data["cv"]["sections"]["experience"][0]
        self.assertEqual(len(exp["highlights"]), 3)
        self.assertIn("summary", exp)

    def test_no_summary_when_bullets_only(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        exp = data["cv"]["sections"]["experience"][0]
        self.assertNotIn("summary", exp)

    def test_removes_existing_summary_when_bullets_only(self):
        yaml_with_summary = SAMPLE_YAML.replace(
            "        highlights:\n          - Built core platform services.",
            "        summary: Old summary.\n        highlights:\n          - Built core platform services.",
        )
        result = apply_experience_rewrite(yaml_with_summary, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        exp = data["cv"]["sections"]["experience"][0]
        self.assertNotIn("summary", exp)

    def test_multi_line_summary_joined(self):
        rewrite = "First sentence.\nSecond sentence.\n\n- Bullet one."
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", rewrite)
        data = self._load(result)
        self.assertEqual(data["cv"]["sections"]["experience"][0]["summary"], "First sentence. Second sentence.")

    # --- errors ---

    def test_raises_when_company_not_found(self):
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_rewrite(SAMPLE_YAML, "Unknown Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)

    def test_raises_when_position_not_found(self):
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Wrong Title", REWRITE_BULLETS_ONLY)

    def test_raises_when_no_experience_section(self):
        yaml_no_exp = "cv:\n  name: Jane\n  sections:\n    summary:\n      - Summary here.\n"
        with self.assertRaises(ExperienceNotFoundError):
            apply_experience_rewrite(yaml_no_exp, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)

    # --- structural ---

    def test_output_is_valid_yaml(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        self.assertIn("cv", data)

    def test_preserves_other_cv_fields(self):
        result = apply_experience_rewrite(SAMPLE_YAML, "Acme Corp", "Senior Engineer", REWRITE_BULLETS_ONLY)
        data = self._load(result)
        self.assertEqual(data["cv"]["name"], "Jane Smith")
