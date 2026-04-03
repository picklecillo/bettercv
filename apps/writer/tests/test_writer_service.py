from unittest.mock import MagicMock

import anthropic
from django.test import TestCase


class WriterServiceTests(TestCase):

    def _make_service(self, chunks=None):
        from apps.writer.writer_service import WriterService
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter(chunks or ["full_name: John\n", "email: j@j.com\n"])
        client.messages.stream.return_value = stream_ctx
        return WriterService(client)

    def test_stream_yaml_yields_prefill_then_chunks(self):
        from apps.writer.writer_service import _PREFILL
        service = self._make_service(["chunk1", "chunk2"])
        result = list(service.stream_yaml("My resume text"))
        self.assertEqual(result, [_PREFILL, "chunk1", "chunk2"])

    def test_stream_yaml_passes_resume_as_user_message(self):
        from apps.writer.writer_service import WriterService
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter([])
        client.messages.stream.return_value = stream_ctx
        service = WriterService(client)

        list(service.stream_yaml("My actual resume"))

        messages = client.messages.stream.call_args.kwargs["messages"]
        user_messages = [m for m in messages if m["role"] == "user"]
        self.assertEqual(user_messages[0]["content"], "My actual resume")

    def test_stream_yaml_sends_prefill_as_assistant_message(self):
        from apps.writer.writer_service import WriterService, _PREFILL
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter([])
        client.messages.stream.return_value = stream_ctx
        service = WriterService(client)

        list(service.stream_yaml("resume"))

        messages = client.messages.stream.call_args.kwargs["messages"]
        assistant_messages = [m for m in messages if m["role"] == "assistant"]
        self.assertEqual(len(assistant_messages), 1)
        self.assertEqual(assistant_messages[0]["content"], _PREFILL)

    def test_stream_yaml_uses_correct_model_and_max_tokens(self):
        from apps.writer.writer_service import WriterService, _MAX_TOKENS
        from apps.shared.claude import MODEL as _MODEL
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter([])
        client.messages.stream.return_value = stream_ctx
        service = WriterService(client)

        list(service.stream_yaml("resume"))

        client.messages.stream.assert_called_once()
        call_kwargs = client.messages.stream.call_args.kwargs
        self.assertEqual(call_kwargs["model"], _MODEL)
        self.assertEqual(call_kwargs["max_tokens"], _MAX_TOKENS)
