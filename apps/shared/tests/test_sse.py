"""Tests for apps.shared.sse — the SSE streaming abstraction."""
from django.test import TestCase

from apps.shared.sse import SSEEvent, SseStream, _default_finalizer, _encode, make_sse_response, no_credits_response


def _collect(stream: SseStream) -> list[str]:
    """Consume a SseStream's response and return raw SSE frames."""
    return list(stream._generate())


def _parse_frames(frames: list[str]) -> list[SSEEvent]:
    """Parse raw SSE wire frames into SSEEvent objects for assertions."""
    events = []
    for frame in frames:
        lines = frame.strip().split("\n")
        event_name = None
        data_lines = []
        for line in lines:
            if line.startswith("event: "):
                event_name = line[len("event: "):]
            elif line.startswith("data: "):
                data_lines.append(line[len("data: "):])
        if event_name is not None:
            events.append(SSEEvent(event=event_name, data="\n".join(data_lines)))
    return events


class EncodeTests(TestCase):
    def test_single_line(self):
        frame = _encode(SSEEvent("chunk", "<span>hello</span>"))
        self.assertEqual(frame, "event: chunk\ndata: <span>hello</span>\n\n")

    def test_multiline_data_split(self):
        frame = _encode(SSEEvent("render", "<p>line one</p>\n<p>line two</p>"))
        self.assertIn("data: <p>line one</p>\n", frame)
        self.assertIn("data: <p>line two</p>\n", frame)

    def test_empty_data(self):
        frame = _encode(SSEEvent("done", ""))
        self.assertEqual(frame, "event: done\ndata: \n\n")


class SseStreamChunkTests(TestCase):
    def test_chunks_emitted_as_chunk_events(self):
        stream = SseStream(source=iter(["hello", "world"]), finalizer=lambda _: iter([]))
        events = _parse_frames(_collect(stream))
        chunk_events = [e for e in events if e.event == "chunk"]
        self.assertEqual(len(chunk_events), 2)
        self.assertIn("hello", chunk_events[0].data)
        self.assertIn("world", chunk_events[1].data)

    def test_chunks_are_html_escaped(self):
        stream = SseStream(source=iter(["<script>alert(1)</script>"]), finalizer=lambda _: iter([]))
        events = _parse_frames(_collect(stream))
        chunk = next(e for e in events if e.event == "chunk")
        self.assertNotIn("<script>", chunk.data)
        self.assertIn("&lt;script&gt;", chunk.data)

    def test_newlines_converted_to_br(self):
        stream = SseStream(source=iter(["line one\nline two"]), finalizer=lambda _: iter([]))
        events = _parse_frames(_collect(stream))
        chunk = next(e for e in events if e.event == "chunk")
        self.assertIn("<br>", chunk.data)

    def test_done_is_always_last(self):
        stream = SseStream(source=iter(["hello"]), finalizer=lambda _: iter([]))
        events = _parse_frames(_collect(stream))
        self.assertEqual(events[-1].event, "done")

    def test_done_emitted_with_empty_source(self):
        stream = SseStream(source=iter([]), finalizer=lambda _: iter([]))
        events = _parse_frames(_collect(stream))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event, "done")


class SseStreamAccumulationTests(TestCase):
    def test_accumulated_text_passed_to_finalizer(self):
        received = []

        def finalizer(text):
            received.append(text)
            return iter([])

        stream = SseStream(source=iter(["foo", "bar"]), finalizer=finalizer)
        _collect(stream)
        self.assertEqual(received, ["foobar"])

    def test_no_accumulation_passes_none_to_finalizer(self):
        received = []

        def finalizer(text):
            received.append(text)
            return iter([])

        stream = SseStream(source=iter(["foo", "bar"]), finalizer=finalizer, accumulate=False)
        _collect(stream)
        self.assertEqual(received, [None])


class SseStreamErrorTests(TestCase):
    def test_known_error_emits_error_chunk_then_done(self):
        class MyError(Exception):
            pass

        def bad_source():
            raise MyError("something went wrong")
            yield  # make it a generator

        stream = SseStream(source=bad_source(), known_errors=(MyError,))
        events = _parse_frames(_collect(stream))
        self.assertEqual(events[0].event, "chunk")
        self.assertIn("result-error", events[0].data)
        self.assertIn("something went wrong", events[0].data)
        self.assertEqual(events[-1].event, "done")

    def test_unexpected_error_emits_error_chunk_then_done(self):
        def bad_source():
            raise RuntimeError("boom")
            yield

        stream = SseStream(source=bad_source())
        events = _parse_frames(_collect(stream))
        self.assertEqual(events[0].event, "chunk")
        self.assertIn("Unexpected error", events[0].data)
        self.assertIn("boom", events[0].data)
        self.assertEqual(events[-1].event, "done")

    def test_error_passes_none_to_finalizer(self):
        received = []

        def finalizer(text):
            received.append(text)
            return iter([])

        def bad_source():
            raise RuntimeError("oops")
            yield

        stream = SseStream(source=bad_source(), finalizer=finalizer)
        _collect(stream)
        self.assertEqual(received, [None])

    def test_finalizer_exception_emits_error_chunk_then_done(self):
        def bad_finalizer(text):
            raise RuntimeError("finalizer blew up")
            yield

        stream = SseStream(source=iter(["ok"]), finalizer=bad_finalizer)
        events = _parse_frames(_collect(stream))
        error_events = [e for e in events if e.event == "chunk" and "result-error" in e.data]
        self.assertTrue(error_events)
        self.assertIn("Post-processing error", error_events[0].data)
        self.assertEqual(events[-1].event, "done")

    def test_done_emitted_even_when_finalizer_raises(self):
        def bad_finalizer(text):
            raise RuntimeError("crash")
            yield

        stream = SseStream(source=iter(["x"]), finalizer=bad_finalizer)
        events = _parse_frames(_collect(stream))
        self.assertEqual(events[-1].event, "done")


class SseStreamFinalizerTests(TestCase):
    def test_finalizer_events_emitted_before_done(self):
        def finalizer(text):
            yield SSEEvent("metadata", "<tr>row</tr>")
            yield SSEEvent("wrap", "<div>content</div>")

        stream = SseStream(source=iter(["text"]), finalizer=finalizer)
        events = _parse_frames(_collect(stream))
        names = [e.event for e in events]
        self.assertEqual(names, ["chunk", "metadata", "wrap", "done"])

    def test_finalizer_event_ordering_is_preserved(self):
        """metadata must precede wrap — structural guarantee via yield order."""
        order = []

        def finalizer(text):
            yield SSEEvent("metadata", "meta")
            order.append("metadata")
            yield SSEEvent("wrap", "wrap")
            order.append("wrap")

        stream = SseStream(source=iter(["x"]), finalizer=finalizer)
        _collect(stream)
        self.assertEqual(order, ["metadata", "wrap"])


class DefaultFinalizerTests(TestCase):
    def test_renders_markdown(self):
        events = list(_default_finalizer("**bold**"))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].event, "render")
        self.assertIn("<strong>bold</strong>", events[0].data)

    def test_empty_string_yields_nothing(self):
        events = list(_default_finalizer(""))
        self.assertEqual(events, [])

    def test_none_yields_nothing(self):
        events = list(_default_finalizer(None))
        self.assertEqual(events, [])

    def test_default_finalizer_used_when_none_passed(self):
        stream = SseStream(source=iter(["**hello**"]))
        events = _parse_frames(_collect(stream))
        render_events = [e for e in events if e.event == "render"]
        self.assertEqual(len(render_events), 1)
        self.assertIn("<strong>hello</strong>", render_events[0].data)


class NoCreditsResponseTests(TestCase):
    def test_emits_error_chunk_then_done(self):
        response = no_credits_response()
        frames = list(response.streaming_content)
        # streaming_content yields bytes
        raw = b"".join(frames).decode()
        self.assertIn("event: chunk", raw)
        self.assertIn("credits-error", raw)
        self.assertIn("event: done", raw)
        # done must be last event
        self.assertGreater(raw.index("event: done"), raw.index("event: chunk"))

    def test_correct_headers(self):
        response = no_credits_response()
        self.assertEqual(response["Cache-Control"], "no-cache")
        self.assertEqual(response["X-Accel-Buffering"], "no")
        self.assertEqual(response["Content-Type"], "text/event-stream")


class MakeSseResponseTests(TestCase):
    def test_sets_content_type(self):
        response = make_sse_response(iter([]))
        self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_sets_cache_control(self):
        response = make_sse_response(iter([]))
        self.assertEqual(response["Cache-Control"], "no-cache")

    def test_sets_accel_buffering(self):
        response = make_sse_response(iter([]))
        self.assertEqual(response["X-Accel-Buffering"], "no")

    def test_streams_generator_content(self):
        def gen():
            yield b"hello"
            yield b" world"
        response = make_sse_response(gen())
        content = b"".join(response.streaming_content)
        self.assertEqual(content, b"hello world")


class SseStreamResponseTests(TestCase):
    def test_response_has_correct_content_type(self):
        stream = SseStream(source=iter([]))
        response = stream.response()
        self.assertEqual(response["Content-Type"], "text/event-stream")

    def test_response_has_cache_control(self):
        stream = SseStream(source=iter([]))
        response = stream.response()
        self.assertEqual(response["Cache-Control"], "no-cache")

    def test_response_has_accel_buffering(self):
        stream = SseStream(source=iter([]))
        response = stream.response()
        self.assertEqual(response["X-Accel-Buffering"], "no")
