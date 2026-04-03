# RFC: Typed Session Stores

## Problem

The Django session is used as an implicit schema across all apps. Key strings like
`session["coach"]["conversations"][str(exp_index)]` and `session["compare"]["jds"][jd_id]`
are known only by convention. There is no validation, no type safety, and test setup
requires manually constructing nested dicts whose shape can only be inferred from views.

Concrete friction points today:

- `_is_stale()` is copy-pasted verbatim in `coach/views.py` and `compare/views.py`
- `session["coach"]["conversations"]` uses `str(exp_index)` as a key — an implementation
  detail that leaks into every caller
- `request.session.modified = True` + `request.session.save()` inside the coach stream
  generator are easy to forget and have caused bugs (documented in CLAUDE.md)
- Every view test has a `_seed_*_session()` helper that manually constructs the nested
  dict; when the schema changes, these helpers produce confusing failures

---

## Chosen Design: Factory Functions Returning Typed Stores (Design A + one steal)

Four factory functions are the entire public surface. Each takes a bare `dict` (Django's
`request.session` or a plain `{}` in tests) and returns a domain object.

```python
# apps/shared/session.py  (replaces the current 49-line module)

def shared(session: dict) -> SharedStore: ...
def coach(session: dict) -> CoachStore: ...
def compare(session: dict) -> CompareStore: ...
def nonce(session: dict) -> NonceStore: ...
```

### SharedStore

```python
class SharedStore:
    def __init__(self, session: dict) -> None: ...

    @property
    def resume_text(self) -> str | None: ...
    @property
    def resume_version(self) -> int | None: ...

    def set_resume(self, text: str) -> None: ...       # bumps version internally
    def clear(self) -> None: ...

    @property
    def yaml(self) -> str | None: ...
    def set_yaml(self, yaml_str: str) -> None: ...

    @property
    def html(self) -> str | None: ...
    def set_html(self, html_str: str) -> None: ...

    def panel_context(self) -> dict: ...
```

### CoachStore

```python
class CoachStore:
    def __init__(self, session: dict) -> None: ...

    @property
    def exists(self) -> bool: ...
    def is_stale(self, shared: SharedStore) -> bool: ...

    @property
    def experiences(self) -> list[dict]: ...
    @property
    def cv_text(self) -> str: ...

    def initialize(
        self,
        cv_text: str,
        experiences: list[dict],
        resume_version: int | None,
        *,
        preserve_conversations: bool = True,
    ) -> None: ...

    def get_conversation(self, exp_index: int) -> list[dict]: ...

    def save_conversation(
        self,
        exp_index: int,
        messages: list[dict],
    ) -> None: ...
    # ↑ Steal from Design C: calls session.save() internally when the session
    #   object has a save() method (i.e. in production, not in plain-dict tests).
    #   This absorbs the generator footgun documented in CLAUDE.md.
```

### CompareStore

```python
class CompareStore:
    def __init__(self, session: dict) -> None: ...

    @property
    def exists(self) -> bool: ...
    def is_stale(self, shared: SharedStore) -> bool: ...

    def initialize(self, resume_text: str, resume_version: int | None) -> None: ...

    @property
    def resume_text(self) -> str: ...

    def add_jd(self, jd_id: str, jd_text: str) -> None: ...
    def get_jd(self, jd_id: str) -> dict | None: ...
    def set_jd_result(self, jd_id: str, analysis: str, metadata: dict | None) -> None: ...
    def all_jds(self) -> list[tuple[str, dict]]: ...
```

### NonceStore

```python
class NonceStore:
    def __init__(self, session: dict) -> None: ...

    def put(self, payload: dict) -> str: ...      # generates UUID, stores, returns key
    def pop(self, key: str) -> dict | None: ...   # consumes the nonce (gone after first read)
```

---

## What Is Hidden

Callers no longer need to know:

- Any session key string (`"coach"`, `"compare"`, `"shared_resume"`, `"conversations"`, etc.)
- Nesting depth or access patterns
- `str(exp_index)` coercion for conversation keys
- `session.modified = True` on mutations
- `session.save()` inside streaming generators (absorbed by `save_conversation`)
- `preserve_conversations` logic on re-parse
- `shared_version > tool_version` with `None`-guard (absorbed by `is_stale`)
- `str(uuid.uuid4())` nonce generation

---

## Dependency Strategy

**In-process.** The stores wrap a plain `dict`. Django's `request.session` is a dict
subclass and satisfies the contract without an adapter. Tests use `{}` directly.

```python
# Production
from apps.shared import session as sess

store = sess.coach(request.session)
store.initialize(cv_text=cv_text, experiences=experiences, resume_version=version)

# Test — no Django, no DB, no session middleware
session = {}
store = sess.coach(session)
store.initialize(cv_text="Alice's resume", experiences=[...], resume_version=1)
assert store.exists is True
assert store.get_conversation(0) == []
```

The `save_conversation` `session.save()` call uses a `hasattr` guard so it is a no-op
when the passed object is a plain dict (test environment).

---

## Testing Strategy

### New boundary tests to write

- `SharedStore.set_resume()` increments version; `resume_version` reflects it
- `SharedStore.panel_context()` returns all three keys
- `CoachStore.is_stale()` returns `True` when shared version is higher
- `CoachStore.initialize()` with `preserve_conversations=True` keeps existing history
- `CoachStore.save_conversation()` appends to the right index; calling it on a real
  Django session object triggers `session.save()`
- `NonceStore.pop()` returns `None` on second call (consumed)

### Old tests to delete / simplify

- All `_seed_*_session()` helpers in view tests — replace with store `initialize()` calls
- The duplicated `_is_stale()` function tests (currently implicit in view tests) — covered
  by store unit tests
- Any test that asserts on raw session key strings like `response.client.session["coach"]`
  — replace with assertions through the store interface

### Test environment needs

None. Stores take a plain dict; no local stand-ins required.

---

## Migration Path

1. **Write `apps/shared/session.py` as the new module** — new classes alongside the existing
   helper functions initially (no callers broken yet).
2. **Migrate `coach/views.py`** — replace raw dict access and `_is_stale()` with store calls.
   Delete the `_is_stale()` helper.
3. **Migrate `compare/views.py`** — same. Delete its `_is_stale()` copy.
4. **Migrate `writer/views.py` and `analyzer/views.py`** — lighter touch (shared resume reads
   and nonce pattern only).
5. **Delete the old helper functions** from `shared/session.py` once no callers remain.
6. **Update view tests** — replace `_seed_*_session()` helpers with store calls.

Each step is independently deployable and testable.

---

## What the Module Owns

- The complete session key namespace (no string keys appear outside this module)
- Version-increment logic for the shared resume
- Stale-detection logic (one implementation, shared by coach and compare)
- Conversation index coercion (`int` → `str` key)
- `session.save()` inside streaming generators
- Nonce UUID generation and single-use enforcement

## What It Exposes

Four factory functions and their return types. That is the contract.

## What It Does Not Own

- `request.session.save()` in non-streaming contexts (Django middleware handles it)
- The content or shape of stored data (e.g. the `WorkExperience` dict schema — that
  stays in `coach/`)
- Any HTML or template rendering
