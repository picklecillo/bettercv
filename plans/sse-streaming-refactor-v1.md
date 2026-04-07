# SSE Streaming Abstraction — Refactor Plan

## Problem

All four stream views (analyzer, coach, compare, writer) duplicate the same SSE generator
skeleton. The duplication is not cosmetic — it carries real risk:

- The SSE wire format (`event: X\ndata: Y\n\n`, multi-line data splitting) is written four
  times. One typo in one place silently breaks streaming for that tool.
- `Cache-Control: no-cache` and `X-Accel-Buffering: no` headers are required on every SSE
  response. The writer view is currently missing `X-Accel-Buffering: no`.
- If the stream source errors after the generator has already started, every view must
  independently ensure it still emits `done` — otherwise the HTMX `EventSource` is orphaned.
  The current views handle this inconsistently.
- The event ordering constraint in the compare view (`metadata` must precede `wrap`) lives as
  a comment next to two yield statements. It is structurally invisible and easy to violate.
- Testing that Compare emits `metadata` before `wrap` requires parsing raw SSE strings from a
  full view integration test. There is no unit-level test for this invariant.

## Chosen Interface

Design B (typed `SSEEvent` objects) with the `str | None` finalizer argument from Design C.

### Core types

```python
# apps/shared/sse.py

from __future__ import annotations

from collections.abc import Callable, Generator, Iterable
from dataclasses import dataclass, field
from typing import Iterator

from django.http import StreamingHttpResponse
from django.utils.html import escape


@dataclass(frozen=True)
class SSEEvent:
    """A single SSE event. Tests assert on these objects — not on raw wire strings."""
    event: str  # e.g. "chunk", "done", "wrap", "metadata", "render", "error"
    data: str   # pre-rendered HTML or text


# Finalizer: called once with accumulated text (None if source errored).
# Must yield SSEEvent objects in the order they must be sent.
# The framework appends DoneEvent after the finalizer exhausts.
Finalizer = Callable[[str | None], Generator[SSEEvent, None, None]]


class SseStream:
    def __init__(
        self,
        *,
        source: Iterable[str],
        finalizer: Finalizer | None = None,
        accumulate: bool = True,
        known_errors: tuple[type[Exception], ...] = (),
    ) -> None: ...

    def response(self) -> StreamingHttpResponse: ...
```

### Wire encoding (internal)

```python
def _encode(event: SSEEvent) -> str:
    lines = "\n".join(f"data: {line}" for line in event.data.splitlines())
    return f"event: {event.event}\n{lines}\n\n"
```

### `_generate` (internal)

```python
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
    finalizer = self._finalizer or _default_finalizer

    try:
        for event in finalizer(text):
            yield _encode(event)
    except Exception as e:
        yield _encode(SSEEvent("chunk", f"<div class='result-error'>Post-processing error: {escape(str(e))}</div>"))

    yield _encode(SSEEvent("done", ""))
```

### Default finalizer (markdown → `render` event)

```python
def _default_finalizer(accumulated: str | None) -> Generator[SSEEvent, None, None]:
    if accumulated:
        import markdown as md
        rendered = md.markdown(accumulated, extensions=["tables"])
        yield SSEEvent("render", rendered)
```

### `response()` (public)

```python
def response(self) -> StreamingHttpResponse:
    r = StreamingHttpResponse(self._generate(), content_type="text/event-stream")
    r["Cache-Control"] = "no-cache"
    r["X-Accel-Buffering"] = "no"
    return r
```

### No-credits helper

```python
def no_credits_response() -> StreamingHttpResponse:
    """Emit a credits-error chunk + done. Used by all four stream views."""
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
```

## How Each Tool Migrates

### Analyzer

```python
# Before: 23-line event_stream() generator + manual StreamingHttpResponse
# After:
return SseStream(
    source=get_service().stream(data["resume_text"], data["jd_text"]),
    known_errors=(ClaudeServiceError,),
).response()
# Default finalizer handles accumulate → markdown → render event.
```

### Writer

```python
# Writer chunks are raw YAML — wrap source in an adapter that pre-formats them,
# so the stream engine's chunk_transform isn't needed.
def _yaml_source(raw_source):
    for chunk in raw_source:
        # chunk is already multi-line YAML; emit as-is, not as escaped HTML
        yield chunk  # SseStream will escape — but Writer chunks aren't prose HTML

# Actually Writer needs a custom chunk encoding. Two clean options:
# Option A: wrap source to pre-escape YAML chunks as code blocks
# Option B: Writer uses a custom finalizer that assembles YAML differently

# Simplest: since Writer has no post-stream action, use accumulate=False
# and a no-op finalizer. The chunk event just carries raw YAML lines.
# The frontend YAML editor reads them directly (it doesn't render HTML spans).
# Revisit if Writer needs rich chunk formatting.

return SseStream(
    source=get_writer_service().stream_yaml(resume_text),
    accumulate=False,
    finalizer=lambda _: iter([]),  # no post-stream events
).response()
```

Note: review Writer's frontend to confirm how it consumes `chunk` events before
finalizing this migration. The current view emits `event: chunk\ndata: line\ndata: line\n\n`
(multi-line data for YAML), which the default `_generate` loop handles correctly via
`_encode`'s splitlines logic — no special case needed.

### Coach

```python
def stream(request):
    # ... nonce pop, credit deduction, session loading ...

    coach_store = sess.coach(request.session)
    exp_index = nonce_data["exp_index"]
    messages_to_send = existing_history + [{"role": "user", "content": nonce_data["user_message"]}]

    def finalizer(accumulated: str | None) -> Generator[SSEEvent, None, None]:
        if accumulated is None:
            return  # error already emitted as chunk

        # Persist conversation before yielding any events
        final_messages = messages_to_send + [{"role": "assistant", "content": accumulated}]
        coach_store.save_conversation(exp_index, final_messages)

        # Extract <rewrite> block
        rewrite_match = re.search(r'<rewrite>(.*?)</rewrite>', accumulated, re.DOTALL | re.IGNORECASE)
        if rewrite_match:
            rewrite_text = rewrite_match.group(1).strip()
            clean = re.sub(r'<rewrite>(.*?)</rewrite>', r'\1', accumulated, flags=re.DOTALL | re.IGNORECASE).strip()
        else:
            rewrite_text = None
            clean = accumulated

        safe = escape(clean).replace("\n", "<br>")
        rewrite_attr = ""
        if rewrite_text:
            val = escape(rewrite_text).replace('\n', '&#10;').replace('\r', '&#13;')
            rewrite_attr = f' data-rewrite="{val}"'

        wrapped = (
            f'<div class="chat-msg assistant-msg"{rewrite_attr} id="msg-{key}">'
            f'<div class="msg-body">{safe}</div>'
            f'</div>'
        )
        yield SSEEvent("wrap", wrapped)

    return SseStream(
        source=get_coach_service().stream_reply(experience, messages_to_send),
        finalizer=finalizer,
    ).response()
```

### Compare

```python
def stream(request):
    # ... nonce pop, credit deduction, session loading ...

    compare_store = sess.compare(request.session)

    def finalizer(accumulated: str | None) -> Generator[SSEEvent, None, None]:
        if accumulated is None:
            return

        metadata_dict = None
        score_high_val = -1
        try:
            meta = get_compare_service().extract_metadata(accumulated, jd_text)
            metadata_dict = {"company": meta.company, "title": meta.title,
                             "score_low": meta.score_low, "score_high": meta.score_high}
            score_high_val = meta.score_high
            label = f"{escape(meta.company)} · {escape(meta.title)}"
            score = f"{meta.score_low}–{meta.score_high} / 100"
        except CompareMetadataError:
            label = "—"
            score = "—"

        compare_store.set_jd_result(jd_id, accumulated, metadata_dict)

        # ORDERING: metadata MUST be yielded before wrap.
        # This is now structurally enforced — wrong order = wrong yield order.
        yield SSEEvent("metadata", _build_summary_row(jd_id, jd_num, label, score, score_high_val))
        yield SSEEvent("wrap", f'<div class="analysis-result">{md.markdown(accumulated, extensions=["tables"])}</div>')

    return SseStream(
        source=get_compare_service().stream_analysis(resume_text, jd_text),
        finalizer=finalizer,
    ).response()
```

## Implementation Steps

### Step 1 — Create `apps/shared/sse.py`

Write the module with `SSEEvent`, `SseStream`, `_encode`, `_generate`, `_default_finalizer`,
`no_credits_response`. No existing code is touched in this step.

Write unit tests in `apps/shared/tests/test_sse.py`:

- `SseStream` with a simple source yields correct chunk events
- Default finalizer renders markdown and emits `render` event
- Known errors are caught and emit error chunk then `done`
- Unexpected exceptions emit error chunk then `done`
- `done` is always the last event, including when finalizer raises
- Passing `accumulated=None` to `_default_finalizer` yields nothing
- Typed `SSEEvent` objects from a custom finalizer are encoded correctly

### Step 2 — Migrate Analyzer

Replace `event_stream()` + manual `StreamingHttpResponse` in `analyzer/views.py` with
`SseStream(...).response()`. Replace no-credits inline generator with `no_credits_response()`.

Run `make test` — existing analyzer view tests must pass unchanged.

### Step 3 — Migrate Writer

Replace `event_stream()` in `writer/views.py`. Confirm Writer's frontend YAML chunk
handling is compatible with `SseStream`'s default encoding before migrating.

Run `make test`.

### Step 4 — Migrate Coach

Replace the coach stream view's generator. Extract `finalizer` as a named inner function
(not a lambda) so it can be unit-tested directly:

```python
# In tests:
events = list(coach_finalizer("Some reply with <rewrite>improved text</rewrite>"))
assert events[0] == SSEEvent("wrap", ...)
assert "data-rewrite=" in events[0].data
```

Delete the existing `test_views.py` stream test that exercises this path through the full
view — it is replaced by the finalizer unit test.

### Step 5 — Migrate Compare

Replace the compare stream view's generator. Write a direct finalizer test:

```python
events = list(compare_finalizer("Full analysis text"))
assert events[0].event == "metadata"   # ordering enforced
assert events[1].event == "wrap"
```

This test didn't exist before — it's new coverage that directly verifies the load-bearing
ordering constraint.

### Step 6 — Delete dead code

- Remove the four inline `event_stream()` generators
- Remove the four `no_credits()` inline generators
- Confirm `X-Accel-Buffering` is now set correctly on Writer (was missing before)
- Remove any view test that tested SSE scaffolding behavior now covered by `test_sse.py`

## What the Module Owns

- SSE wire format: `event: X\ndata: Y\n\n`, multi-line data line-splitting
- `StreamingHttpResponse` construction + required headers
- Chunk accumulation + the `"".join()` at the end
- Error normalisation: known exceptions vs. unexpected, both emit a chunk then `done`
- `done` guarantee: always the last event, even if `finalizer` raises
- The default markdown-render-to-`render`-event pattern

## What It Does Not Own

- HTML construction (finalizers build their own HTML strings)
- Session reads/writes (finalizers close over session store references)
- Secondary API calls (e.g., `extract_metadata` — finalizer calls it directly)
- Credit deduction (stays in the view, before `SseStream` is constructed)
- Nonce validation (stays in the view)

## Tests to Write (new)

| Test | Location | Replaces |
|---|---|---|
| `SseStream` core behavior (chunk/done/error) | `shared/tests/test_sse.py` | Nothing — new |
| `_default_finalizer` markdown rendering | `shared/tests/test_sse.py` | Nothing — new |
| Coach finalizer: rewrite extraction + session save | `coach/tests/test_views.py` or `test_coach_finalizer.py` | Partial view test |
| Compare finalizer: `metadata` before `wrap` ordering | `compare/tests/test_views.py` or `test_compare_finalizer.py` | Nothing — new |

## Tests to Delete (made redundant)

- Any view test that asserts on raw `event: chunk\ndata:...` string output can be
  replaced by a finalizer unit test asserting on `SSEEvent` objects, if that coverage
  is now duplicated. Keep view-level tests that test the full request/response cycle
  (nonce validation, credit deduction, session loading).
