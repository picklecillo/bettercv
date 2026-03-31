# PRD: Coach "Apply to Resume" Button

## Problem Statement

When the Resume Coach proposes a rewritten bullet list for a work experience, the user can only copy the text to their clipboard. To actually update their resume, they must manually switch to the Resume Writer tab, locate the correct experience entry in the YAML editor, and paste the bullets in. This context switch is disruptive and error-prone — users have to reformat the text as YAML highlights by hand, and it's easy to edit the wrong experience entry.

## Solution

Add an "Apply to Resume" button next to the existing COPY button in the coach's "Updated description" panel. Clicking it sends the proposed rewrite to a backend endpoint that finds the matching experience entry in the shared YAML and replaces its `highlights` list with the new bullets. The user gets inline confirmation that the YAML was updated.

If no YAML exists yet (the user hasn't run the Writer tool), the button is disabled with a tooltip explaining why.

## User Stories

1. As a resume coach user, I want to apply a proposed bullet rewrite directly to my resume YAML, so that I don't have to manually copy-paste and reformat bullets in the Writer tab.
2. As a resume coach user, I want the "Apply to Resume" button to only be available when a rewrite has been proposed, so that I don't accidentally trigger it with no content.
3. As a resume coach user, I want to see a clear confirmation after applying a rewrite, so that I know the YAML was updated successfully.
4. As a resume coach user, I want the "Apply to Resume" button to be disabled if no YAML exists yet, so that I understand I need to generate my resume in the Writer first.
5. As a resume coach user, I want the button to show a tooltip when disabled explaining that the Writer tool must be used first, so that I understand what to do.
6. As a resume coach user, I want the YAML update to match the correct experience entry by company name and job title, so that the right role's highlights are replaced.
7. As a resume coach user, I want to continue the coaching conversation after applying a rewrite, so that I can iterate further and apply again.
8. As a resume coach user, I want to apply an updated rewrite a second time if I continue refining the bullets, so that the latest version always wins.
9. As a resume coach user, I want the "Apply to Resume" button to appear at the same level of prominence as the COPY button, so that I can easily find it without it dominating the UI.
10. As a resume coach user, I want the rendered HTML preview in the Writer to reflect the updated bullets the next time I visit the Writer tab, so that my changes are visible without re-running the Writer.
11. As a resume coach user, I want to apply rewrites for multiple experiences independently, so that I can coach each role separately and apply each one.
12. As a resume coach user, I want an error message if the experience cannot be matched in the YAML, so that I understand why the update failed rather than seeing a silent failure.

## Implementation Decisions

### Modules to Build or Modify

**New endpoint: `POST /coach/apply/`**
- Accepts: `exp_index` (integer), the rewrite text (string)
- Looks up the experience from `session["coach"]["experiences"][exp_index]` to get `company` and `title`
- Parses `session["shared_yaml"]` using PyYAML
- Finds the matching experience entry under `cv.sections.experience` by fuzzy-matching `company` and `position` fields (case-insensitive, stripped)
- Replaces the entry's `highlights` list with the lines from the rewrite text (split by newline, stripping leading bullet characters: `-`, `•`, `*`)
- Serialises back to YAML and writes to `session["shared_yaml"]`
- Clears `session["shared_html"]` so the Writer re-renders on next visit
- Returns a JSON response: `{ok: true}` or `{ok: false, error: "..."}` (no HTMX partial needed — JS handles the feedback)
- Returns HTTP 409 if no `shared_yaml` exists in session
- Returns HTTP 404 if no matching experience is found in the YAML

**Coach template (`split_screen.html`)**
- Add "Apply to Resume" button next to the COPY button in the `#we-updated-section` panel
- Button is disabled when `shared_yaml` is absent (passed as a context variable from the view) or when no rewrite is available for this experience
- On click: POST to `/coach/apply/` via `fetch()`, sending the current `weRewrites[activeIdx]` and `exp_index`
- On success: swap button text/icon to a checkmark for 2 seconds, then restore
- On error: show an inline error message below the buttons

**Coach `views.py`**
- Pass a `has_yaml` boolean to the template context so the button's initial disabled state is rendered server-side
- Implement the `apply()` view function wired to the new endpoint

**YAML parsing helper (new function in writer app or shared)**
- `apply_experience_highlights(yaml_str, company, position, highlights) -> str`
- Pure function: takes YAML string, locates the experience by company+position, replaces highlights, returns updated YAML string
- Raises `ExperienceNotFoundError` if no match
- This is the deep module — it can be tested in complete isolation with no Django, no session, no HTTP

### Matching Logic

- Match is case-insensitive and whitespace-stripped on both `company`/`position` (YAML) and `company`/`title` (coach session)
- Exact match preferred; if no exact match, no fuzzy fallback (fail with a clear error)
- If multiple entries share the same company+position, match the first one

### Bullet Parsing

The rewrite text from `<rewrite>` tags may use various bullet prefixes (`-`, `•`, `*`, or none). The apply logic strips these prefixes and any leading/trailing whitespace per line, discards blank lines, and stores each line as a plain string in `highlights`.

### Session Invalidation

After applying, `session["shared_html"]` is cleared (set to `None` or deleted) so the Writer re-renders the preview on next visit. `session["shared_yaml"]` is updated in place. `request.session.save()` is called explicitly (same pattern used elsewhere in streaming views).

## Testing Decisions

**What makes a good test**: Tests should assert on observable HTTP responses and session state changes, not on internal implementation details. Tests for the pure YAML helper should assert on the output YAML string given controlled input, not on how the parsing works internally.

**Modules to test**:

1. **`apply_experience_highlights()` helper**
   - Given a valid YAML string with a matching experience, returns YAML with updated highlights
   - Given a YAML with no matching experience, raises `ExperienceNotFoundError`
   - Handles case-insensitive company/position matching
   - Strips various bullet prefix formats (`-`, `•`, `*`, none)
   - Discards blank lines in the rewrite
   - Does not mutate other YAML fields

2. **`apply()` view**
   - Returns 409 when `shared_yaml` is absent from session
   - Returns 404 when experience is not found in the YAML
   - Returns 200 with `{ok: true}` on success, and `session["shared_yaml"]` reflects the update
   - Clears `session["shared_html"]` on success
   - Uses the same fake/session injection pattern as existing coach view tests

**Prior art**: `apps/coach/tests/test_views.py` for view tests; `apps/writer/tests/` for YAML-related helpers.

## Out of Scope

- Applying rewrites to `summary`, `education`, `projects`, or `skills` sections — only `experience.highlights` for now
- Undo / revert after applying a rewrite
- Diff view showing what changed in the YAML
- Syncing in the other direction (edits in the Writer updating the coach session)
- Fuzzy / partial matching for company or position names
- Auto-applying on every new rewrite (always explicit user action)
- Any changes to the Writer tab UI to show which sections were recently updated

## Further Notes

- The `<rewrite>` extraction already handles newline encoding (`&#10;`) in HTML attributes; the JS layer should decode these before POSTing to the backend.
- The apply endpoint must guard against CSRF in the same way other POST endpoints do (Django's `{% csrf_token %}` or the `X-CSRFToken` header pattern used in fetch calls).
- If the Writer YAML was hand-edited by the user and no longer has an `experience` section at all, the endpoint should return a clear error rather than crashing.
