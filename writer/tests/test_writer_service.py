from unittest.mock import MagicMock

import anthropic
from django.test import TestCase


class WriterServiceTests(TestCase):

    def _make_service(self, chunks=None):
        from writer.writer_service import WriterService
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter(chunks or ["full_name: John\n", "email: j@j.com\n"])
        client.messages.stream.return_value = stream_ctx
        return WriterService(client)

    def test_stream_yaml_yields_chunks(self):
        service = self._make_service(["chunk1", "chunk2"])
        result = list(service.stream_yaml("My resume text"))
        self.assertEqual(result, ["chunk1", "chunk2"])

    def test_stream_yaml_passes_resume_as_user_message(self):
        from writer.writer_service import WriterService
        client = MagicMock(spec=anthropic.Anthropic)
        stream_ctx = MagicMock()
        stream_ctx.__enter__ = lambda s: s
        stream_ctx.__exit__ = MagicMock(return_value=False)
        stream_ctx.text_stream = iter([])
        client.messages.stream.return_value = stream_ctx
        service = WriterService(client)

        list(service.stream_yaml("My actual resume"))

        call_kwargs = client.messages.stream.call_args
        messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0] if call_kwargs.args else call_kwargs.kwargs["messages"]
        self.assertEqual(messages[-1]["content"], "My actual resume")

    def test_stream_yaml_uses_correct_model_and_max_tokens(self):
        from writer.writer_service import WriterService, _MODEL, _MAX_TOKENS
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
