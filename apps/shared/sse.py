from __future__ import annotations

from collections.abc import Callable, Generator, Iterable

import markdown as md
from dataclasses import dataclass
from django.http import StreamingHttpResponse
from django.utils.html import escape


@dataclass(frozen=True)
class SSEEvent:
    """A single SSE event. Tests assert on these objects, not on raw wire strings."""
    event: str  # e.g. "chunk", "done", "wrap", "metadata", "render", "error"
    data: str   # pre-rendered HTML or text


# A finalizer receives the accumulated text (None if the source errored) and
# yields SSEEvent objects in the order they must be sent. The framework appends
# a done event after the finalizer exhausts.
Finalizer = Callable[[str | None], Generator[SSEEvent, None, None]]


def _encode(event: SSEEvent) -> str:
    """Encode an SSEEvent to the SSE wire format."""
    data_lines = event.data.splitlines() or [""]
    lines = "\n".join(f"data: {line}" for line in data_lines)
    return f"event: {event.event}\n{lines}\n\n"


def _default_finalizer(accumulated: str | None) -> Generator[SSEEvent, None, None]:
    """Render accumulated text as markdown and emit a 'render' event."""
    if accumulated:
        rendered = md.markdown(accumulated, extensions=["tables"])
        yield SSEEvent("render", rendered)


class SseStream:
    """
    Owns:
    - SSE wire format encoding
    - StreamingHttpResponse construction with required headers
    - Chunk accumulation
    - Error normalisation (known vs unexpected exceptions both emit chunk + done)
    - Guaranteed done event even if finalizer raises

    Does NOT own:
    - HTML construction (finalizers build their own HTML)
    - Session reads/writes (finalizers close over session store references)
    - Secondary API calls (finalizers call them directly)
    - Credit deduction (stays in the view before SseStream is constructed)
    """

    def __init__(
        self,
        *,
        source: Iterable[str],
        finalizer: Finalizer | None = None,
        accumulate: bool = True,
        known_errors: tuple[type[Exception], ...] = (),
    ) -> None:
        self._source = source
        self._finalizer = finalizer or _default_finalizer
        self._accumulate = accumulate
        self._known_errors = known_errors

    def _generate(self) -> Generator[str, None, None]:
        accumulated: list[str] = []
        errored = False

        try:
            for raw in self._source:
                if self._accumulate:
                    accumulated.append(raw)
                safe = escape(raw).replace("\n", "<br>")
                yield _encode(SSEEvent("chunk", f"<span>{safe}</span>"))

        except self._known_errors as e:
            errored = True
            yield _encode(SSEEvent("chunk", f"<div class='result-error'>{escape(str(e))}</div>"))
        except Exception as e:
            errored = True
            yield _encode(SSEEvent("chunk", f"<div class='result-error'>Unexpected error: {escape(str(e))}</div>"))

        text: str | None = "".join(accumulated) if (self._accumulate and not errored) else None

        try:
            for event in self._finalizer(text):
                yield _encode(event)
        except Exception as e:
            yield _encode(SSEEvent("chunk", f"<div class='result-error'>Post-processing error: {escape(str(e))}</div>"))

        yield _encode(SSEEvent("done", ""))

    def response(self) -> StreamingHttpResponse:
        r = StreamingHttpResponse(self._generate(), content_type="text/event-stream")
        r["Cache-Control"] = "no-cache"
        r["X-Accel-Buffering"] = "no"
        return r


def make_sse_response(generator) -> StreamingHttpResponse:
    """
    Wrap a custom generator in a StreamingHttpResponse with the required SSE headers.
    Use this when SseStream's chunk format doesn't fit (e.g. raw text, not HTML chunks).
    """
    r = StreamingHttpResponse(generator, content_type="text/event-stream")
    r["Cache-Control"] = "no-cache"
    r["X-Accel-Buffering"] = "no"
    return r


def no_credits_response() -> StreamingHttpResponse:
    """Emit a credits-error chunk + done. Used by all stream views."""
    def _gen():
        html = (
            "<div class='result-error credits-error'>No credits remaining. "
            "<a href='/accounts/buy/'>Buy credits</a> to continue.</div>"
        )
        yield _encode(SSEEvent("chunk", html))
        yield _encode(SSEEvent("done", ""))

    r = StreamingHttpResponse(_gen(), content_type="text/event-stream")
    r["Cache-Control"] = "no-cache"
    r["X-Accel-Buffering"] = "no"
    return r
