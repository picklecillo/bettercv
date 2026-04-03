from django.test import TestCase

from apps.shared import session as sess
from apps.shared.session import CoachStore, CompareStore, NonceStore, SharedStore


class SharedStoreTests(TestCase):

    def test_resume_version_none_when_no_resume(self):
        store = SharedStore({})
        self.assertIsNone(store.resume_version)

    def test_set_resume_stores_text_and_bumps_version(self):
        s = {}
        store = SharedStore(s)
        store.set_resume("Alice's resume", filename="alice.pdf")
        self.assertEqual(store.resume_text, "Alice's resume")
        self.assertEqual(store.resume_version, 1)
        self.assertEqual(store.resume["resume_filename"], "alice.pdf")

    def test_set_resume_increments_version_on_second_call(self):
        s = {}
        store = SharedStore(s)
        store.set_resume("v1")
        store.set_resume("v2")
        self.assertEqual(store.resume_version, 2)

    def test_yaml_and_html_roundtrip(self):
        s = {}
        store = SharedStore(s)
        store.set_yaml("cv:\n  name: Alice")
        store.set_html("<p>Alice</p>")
        self.assertEqual(store.yaml, "cv:\n  name: Alice")
        self.assertEqual(store.html, "<p>Alice</p>")

    def test_invalidate_html_removes_html(self):
        s = {}
        store = SharedStore(s)
        store.set_html("<p>old</p>")
        store.invalidate_html()
        self.assertIsNone(store.html)
        self.assertNotIn("shared_html", s)

    def test_panel_context_returns_all_three_keys(self):
        s = {}
        store = SharedStore(s)
        store.set_resume("text")
        store.set_yaml("yaml")
        store.set_html("html")
        ctx = store.panel_context()
        self.assertIn("shared_resume", ctx)
        self.assertIn("shared_yaml", ctx)
        self.assertIn("shared_html", ctx)
        self.assertEqual(ctx["shared_yaml"], "yaml")

    def test_panel_context_missing_keys_return_none(self):
        ctx = SharedStore({}).panel_context()
        self.assertIsNone(ctx["shared_resume"])
        self.assertIsNone(ctx["shared_yaml"])
        self.assertIsNone(ctx["shared_html"])

    def test_factory_function_returns_shared_store(self):
        self.assertIsInstance(sess.shared({}), SharedStore)


class CoachStoreTests(TestCase):

    def test_exists_false_when_no_session(self):
        self.assertFalse(CoachStore({}).exists)

    def test_exists_false_when_empty_experiences(self):
        s = {"coach": {"cv_text": "x", "experiences": [], "conversations": {}, "resume_version": None}}
        self.assertFalse(CoachStore(s).exists)

    def test_exists_true_after_initialize(self):
        s = {}
        store = CoachStore(s)
        store.initialize(cv_text="my cv", experiences=[{"company": "Acme"}], resume_version=1)
        self.assertTrue(store.exists)

    def test_initialize_stores_all_fields(self):
        s = {}
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{"x": 1}], resume_version=3)
        self.assertEqual(store.cv_text, "cv")
        self.assertEqual(store.experiences, [{"x": 1}])
        self.assertEqual(s["coach"]["resume_version"], 3)

    def test_initialize_preserves_existing_conversations_by_default(self):
        s = {"coach": {"cv_text": "old", "experiences": [{}], "conversations": {"0": [{"role": "user"}]}, "resume_version": None}}
        store = CoachStore(s)
        store.initialize(cv_text="new", experiences=[{}], resume_version=None)
        self.assertEqual(store.get_conversation(0), [{"role": "user"}])

    def test_initialize_clears_conversations_when_not_preserving(self):
        s = {"coach": {"cv_text": "old", "experiences": [{}], "conversations": {"0": [{"role": "user"}]}, "resume_version": None}}
        store = CoachStore(s)
        store.initialize(cv_text="new", experiences=[{}], resume_version=None, preserve_conversations=False)
        self.assertEqual(store.get_conversation(0), [])

    def test_get_conversation_returns_empty_list_for_new_index(self):
        s = {}
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=None)
        self.assertEqual(store.get_conversation(0), [])

    def test_save_conversation_persists_messages(self):
        s = {}
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=None)
        messages = [{"role": "user", "content": "hello"}, {"role": "assistant", "content": "hi"}]
        store.save_conversation(0, messages)
        self.assertEqual(store.get_conversation(0), messages)

    def test_save_conversation_uses_str_key_internally(self):
        s = {}
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=None)
        store.save_conversation(2, [{"role": "user", "content": "test"}])
        self.assertIn("2", s["coach"]["conversations"])

    def test_is_stale_false_when_no_shared_version(self):
        s = {}
        shared = SharedStore(s)
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=1)
        self.assertFalse(store.is_stale(shared))

    def test_is_stale_false_when_no_tool_version(self):
        s = {}
        shared = SharedStore(s)
        shared.set_resume("text")
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=None)
        self.assertFalse(store.is_stale(shared))

    def test_is_stale_true_when_shared_newer(self):
        s = {}
        shared = SharedStore(s)
        shared.set_resume("v1")
        shared.set_resume("v2")  # version is now 2
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=1)
        self.assertTrue(store.is_stale(shared))

    def test_is_stale_false_when_versions_match(self):
        s = {}
        shared = SharedStore(s)
        shared.set_resume("v1")  # version 1
        store = CoachStore(s)
        store.initialize(cv_text="cv", experiences=[{}], resume_version=1)
        self.assertFalse(store.is_stale(shared))

    def test_factory_function_returns_coach_store(self):
        self.assertIsInstance(sess.coach({}), CoachStore)


class CompareStoreTests(TestCase):

    def test_is_initialized_false_when_no_session(self):
        self.assertFalse(CompareStore({}).is_initialized)

    def test_is_initialized_true_after_initialize(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        self.assertTrue(store.is_initialized)

    def test_has_jds_false_when_empty(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        self.assertFalse(store.has_jds)

    def test_has_jds_true_after_add_jd(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        store.add_jd("jd-1", "We need engineers.")
        self.assertTrue(store.has_jds)

    def test_jd_count_increments(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        self.assertEqual(store.jd_count(), 0)
        store.add_jd("jd-1", "Job A")
        self.assertEqual(store.jd_count(), 1)
        store.add_jd("jd-2", "Job B")
        self.assertEqual(store.jd_count(), 2)

    def test_get_jd_returns_none_for_unknown_id(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        self.assertIsNone(store.get_jd("nonexistent"))

    def test_set_jd_result_stores_analysis_and_metadata(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        store.add_jd("jd-1", "Job text")
        meta = {"company": "Acme", "title": "Eng", "score_low": 70, "score_high": 80}
        store.set_jd_result("jd-1", "Analysis text", meta)
        jd = store.get_jd("jd-1")
        self.assertEqual(jd["analysis"], "Analysis text")
        self.assertEqual(jd["metadata"]["company"], "Acme")

    def test_set_jd_result_with_none_metadata(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        store.add_jd("jd-1", "Job text")
        store.set_jd_result("jd-1", "Analysis", None)
        self.assertIsNone(store.get_jd("jd-1")["metadata"])

    def test_all_jds_returns_ordered_list(self):
        s = {}
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=None)
        store.add_jd("id-1", "Job 1")
        store.add_jd("id-2", "Job 2")
        jds = store.all_jds()
        self.assertEqual(len(jds), 2)
        self.assertEqual(jds[0][0], "id-1")
        self.assertEqual(jds[1][0], "id-2")

    def test_is_stale_true_when_shared_newer(self):
        s = {}
        shared = SharedStore(s)
        shared.set_resume("v1")
        shared.set_resume("v2")  # version 2
        store = CompareStore(s)
        store.initialize(resume_text="r", resume_version=1)
        self.assertTrue(store.is_stale(shared))

    def test_factory_function_returns_compare_store(self):
        self.assertIsInstance(sess.compare({}), CompareStore)


class NonceStoreTests(TestCase):

    def test_put_returns_a_key(self):
        store = NonceStore({})
        key = store.put({"data": "value"})
        self.assertIsInstance(key, str)
        self.assertTrue(len(key) > 0)

    def test_pop_returns_payload(self):
        s = {}
        store = NonceStore(s)
        key = store.put({"resume_text": "hello"})
        result = store.pop(key)
        self.assertEqual(result["resume_text"], "hello")

    def test_pop_is_single_use(self):
        s = {}
        store = NonceStore(s)
        key = store.put({"x": 1})
        store.pop(key)
        self.assertIsNone(store.pop(key))

    def test_pop_returns_none_for_unknown_key(self):
        store = NonceStore({})
        self.assertIsNone(store.pop("nonexistent"))

    def test_two_nonces_are_independent(self):
        s = {}
        store = NonceStore(s)
        k1 = store.put({"n": 1})
        k2 = store.put({"n": 2})
        self.assertNotEqual(k1, k2)
        self.assertEqual(store.pop(k1)["n"], 1)
        self.assertEqual(store.pop(k2)["n"], 2)

    def test_factory_function_returns_nonce_store(self):
        self.assertIsInstance(sess.nonce({}), NonceStore)
