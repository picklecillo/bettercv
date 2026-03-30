# Plan: Landing Page, Persistent Resume Panel, and Unified YAML Workflow

> Source PRD: `plans/landing-panel-yaml-v1.md`

## Architectural Decisions

- **Routes**: `/` → static marketing page; `/home` → resume entry point (replaces current `/`); `/resume/` POST → upload + YAML generation; `/resume/render/` POST → re-render HTML from YAML; `/resume/build/` POST → download PDF. All tool routes unchanged.
- **Session keys**: `shared_resume` (existing: text + filename), `shared_yaml` (new: full YAML string), `shared_html` (new: rendered HTML string).
- **Panel states**: three states — Upload, Preview, Editor — determined server-side from session contents and returned as HTMX partial swaps.
- **Layout**: shared base template with a fixed 1/3-width left panel and 2/3-width right content area. All tool pages and `/home` extend this base.
- **Service reuse**: panel YAML generation calls `WriterService` and `RenderCVBuilder` directly; no new AI logic introduced.

---

## Phase 1: Marketing Landing Page

**User stories**: 1, 2, 3

### What to build

Move the current `/` route to `/home` and introduce a new static marketing template at `/`. The marketing page has no session logic — it describes the product and all four tools, and provides a CTA button linking to `/home`. The existing home app's upload form and tool cards continue to work at their new `/home` URL.

### Acceptance criteria

- [ ] `GET /` returns a static marketing page with a product headline and descriptions of all four tools.
- [ ] The marketing page has a CTA button that links to `/home`.
- [ ] `GET /home` serves what was previously at `/` (resume upload form or tool cards depending on session state).
- [ ] All existing links and redirects that pointed to `/` now point to `/home`.
- [ ] No session reads or writes occur on the `/` route.

---

## Phase 2: Two-Column Layout + Panel Upload State on `/home`

**User stories**: 4, 5, 6, 14, 15, 16

### What to build

Introduce a shared base template that renders a 1/3-width left panel alongside a 2/3-width right content area. The panel in this phase renders only the Upload state (text area + PDF upload, posting to `/resume/`). Resume submission continues to work as today — it stores resume text in session and returns the panel; no YAML generation yet. The `/home` right column shows CTA cards for Analyzer, Coach, and Compare. The panel partial is wired into the base template so it will be available to all pages that extend it.

### Acceptance criteria

- [ ] All pages that extend the base template render a 1/3-width left panel and a 2/3-width right area.
- [ ] `GET /home` with no resume in session: panel shows the upload form; right column shows tool CTA cards.
- [ ] `GET /home` with a resume in session: panel shows upload form (Preview state comes in Phase 3); right column shows tool CTA cards.
- [ ] Submitting a resume (text or PDF) on `/home` stores the resume text in session and re-renders the panel.
- [ ] The panel upload form accepts both plain text and PDF upload.
- [ ] An error message is shown in the panel if neither text nor PDF is provided.

---

## Phase 3: YAML Generation on Upload + Panel Preview State

**User stories**: 7, 8, 9, 10

### What to build

Extend the `/resume/` POST handler to synchronously generate YAML from the uploaded resume (via `WriterService`) and render HTML from that YAML (via `RenderCVBuilder`), then store both in session. Add session helpers for `shared_yaml` and `shared_html`. After a successful upload, the panel returns in Preview state: it shows the rendered HTML resume with an "Edit YAML" button and a "Download PDF" button. On subsequent page loads, if `shared_html` is present in session, the panel renders directly in Preview state.

### Acceptance criteria

- [ ] Submitting a resume triggers YAML generation and HTML rendering before the response is returned.
- [ ] `shared_yaml` and `shared_html` are stored in session after a successful upload.
- [ ] The panel renders in Preview state (HTML preview + Edit YAML + Download PDF buttons) after upload.
- [ ] `GET` any page with `shared_html` in session: panel renders in Preview state immediately.
- [ ] If YAML generation or HTML rendering fails, the panel returns to Upload state with an error message; no partial session state is left.
- [ ] A loading indicator is shown on the submit button while generation is in progress.

---

## Phase 4: YAML Editor State + Re-Render + PDF Download

**User stories**: 11, 12, 13

### What to build

Add the Editor state to the panel: clicking "Edit YAML" swaps the HTML preview for a YAML textarea pre-populated with `shared_yaml`. Add a `POST /resume/render/` endpoint that accepts `yaml_content`, calls `RenderCVBuilder.render_html()`, updates `shared_html` in session, and returns the panel in Preview state. Add a `POST /resume/build/` endpoint that accepts `yaml_content`, calls `RenderCVBuilder.build_pdf()`, and returns the PDF as a file attachment. Clicking "Preview" in the Editor state posts to `/resume/render/` and transitions back to Preview state.

### Acceptance criteria

- [ ] Clicking "Edit YAML" in the panel replaces the HTML preview with a YAML textarea containing the current `shared_yaml`.
- [ ] The Editor state has a "Preview" button and a "Download PDF" button.
- [ ] Clicking "Preview" posts the current YAML to `/resume/render/`, updates `shared_html` in session, and renders the updated HTML preview in the panel.
- [ ] Clicking "Download PDF" from either Preview or Editor state returns a valid PDF file.
- [ ] A `RenderCVBuildError` from either endpoint returns an error message in the panel without crashing.
- [ ] `/resume/render/` and `/resume/build/` are distinct from `/writer/render/` and `/writer/build/`.

---

## Phase 5: Tool Pages Adopt Shared Layout

**User stories**: 17, 18, 19, 20, 21, 22, 23

### What to build

Update all four tool templates (Analyzer, Coach, Compare, Writer) to extend the shared base template. Remove each tool's individual resume upload section — the left panel now provides that. The panel renders the correct state (Upload or Preview) from session on every tool page load. Add a confirmation prompt when the user attempts to upload a new resume while one is already in session, warning that the current tool state may be affected; on confirmation, all three session keys are replaced.

### Acceptance criteria

- [ ] `GET /analyzer/`, `/coach/`, `/compare/`, `/writer/` all render with the 1/3 panel + 2/3 tool content layout.
- [ ] None of the tool pages contain their own resume upload form.
- [ ] Visiting a tool page with a resume in session shows the panel in Preview state immediately.
- [ ] Visiting a tool page without a resume in session shows the panel in Upload state.
- [ ] Attempting to upload a new resume when one is already in session triggers a confirmation prompt.
- [ ] Confirming the prompt replaces `shared_resume`, `shared_yaml`, and `shared_html` in session and returns the panel in Preview state with the new resume.
- [ ] Cancelling the prompt leaves the existing session state unchanged.
- [ ] Tool navigation links are accessible from within each tool page.
