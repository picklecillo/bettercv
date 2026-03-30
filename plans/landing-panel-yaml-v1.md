# PRD: Landing Page, Persistent Resume Panel, and Unified YAML Workflow

## Problem Statement

BetterCV has no marketing entry point — arriving at `/` drops the user directly into a resume upload form with no context about what the product does or what tools are available. Each tool also maintains its own isolated resume upload section, forcing users to re-upload their resume every time they switch tools. There is no unified resume state visible across the app. Finally, the resume-to-YAML conversion is buried inside the dedicated Writer tool, even though a structured YAML representation of the user's resume is useful for the whole product.

## Solution

Introduce a static marketing landing page at `/` that explains the product and drives users to `/home`. At `/home` and on every tool page, a persistent 1/3-width left panel shows the user's resume state: an upload form when no resume is loaded, or an HTML preview of their rendered resume (generated via RenderCV from Claude-produced YAML) once one is loaded. The panel also allows the user to switch to a YAML editor and back to the preview. All four tool pages adopt a two-column layout (panel + tool content) and remove their individual resume upload sections.

## User Stories

1. As a new visitor, I want to see a marketing landing page at `/` that describes BetterCV and its tools, so that I understand what the product does before I start.
2. As a new visitor, I want a prominent call-to-action on the landing page that takes me to `/home`, so that I know where to begin.
3. As a new visitor, I want each tool briefly described on the landing page, so that I can decide which one I want to use.
4. As a user at `/home`, I want to see an upload form in the left panel, so that I can provide my resume to get started.
5. As a user at `/home`, I want to paste my resume as text or upload a PDF, so that I can use whichever format I have available.
6. As a user at `/home`, I want the right side to show call-to-action cards for the Analyzer, Coach, and Compare tools, so that I can navigate directly to a tool after uploading.
7. As a user, after uploading my resume, I want YAML to be generated automatically in the background (via Claude + RenderCV), so that I do not have to take an extra step.
8. As a user, I want the left panel to show a rendered HTML preview of my resume once the YAML is ready, so that I can see how my resume looks.
9. As a user viewing the HTML preview, I want an "Edit YAML" button, so that I can inspect and modify the underlying YAML.
10. As a user viewing the HTML preview, I want a "Download PDF" button, so that I can export my resume as a PDF at any time.
11. As a user who clicked "Edit YAML", I want the HTML preview to be replaced by a YAML textarea editor, so that I can modify the structured resume content.
12. As a user in the YAML editor, I want a "Preview" button, so that I can re-render the HTML from my updated YAML.
13. As a user who clicks "Preview", I want the YAML editor to be replaced by the updated HTML preview, so that I can see the effect of my edits.
14. As a user navigating to a tool page, I want the left panel to be immediately visible with my resume's HTML preview (if one is already loaded), so that I do not have to re-upload my resume.
15. As a user on a tool page, I want the tool's controls to occupy the right 2/3 of the screen, so that I have a clear workspace.
16. As a user on any tool page, I want the left panel to always be visible, so that I can reference my resume or make edits without leaving the tool.
17. As a user who has loaded a resume and is actively using a tool, I want to be warned before uploading a new resume, so that I do not accidentally lose my current work.
18. As a user who confirms the warning, I want the new resume to replace the old one and generate a new YAML and preview, so that I can switch resumes freely.
19. As a user on the Analyzer page, I want the left panel to show my resume preview instead of a separate resume input, so that the layout is consistent across all tools.
20. As a user on the Coach page, I want the left panel to show my resume preview instead of a separate resume input, so that the layout is consistent.
21. As a user on the Compare page, I want the left panel to show my resume preview instead of a separate resume input, so that the layout is consistent.
22. As a user on the Writer page, I want the left panel to show my resume preview instead of a separate resume input, so that the layout is consistent.
23. As a user, I want all tool navigation links to remain accessible from within each tool page, so that I can switch between tools without returning to the home page.

## Implementation Decisions

### New Pages and URL Changes
- `/` becomes a static marketing page (no session logic). It describes the product and each tool, with a CTA button linking to `/home`.
- `/home` is a new URL replacing the old `/` entry point. It renders the two-column layout (panel + tool CTAs).
- All existing tool URLs (`/analyzer/`, `/coach/`, `/compare/`, `/writer/`) are unchanged.

### Two-Column Base Layout
- A shared base template provides a two-column layout: 1/3-width left panel + 2/3-width right content area.
- All tool pages and `/home` extend this base template.
- The panel renders its own state independently; the right area is filled by each page's content block.
- Mobile layout is out of scope; the two-column layout is desktop-only for now.

### Resume Panel — Three States
The panel is a self-contained partial template with three states managed via HTMX swaps:

1. **Upload state**: form with text area and PDF upload, posts to `/resume/`.
2. **Preview state**: rendered HTML resume + "Edit YAML" button + "Download PDF" button.
3. **Editor state**: YAML textarea + "Preview" button + "Download PDF" button.

State is determined server-side from session contents when the panel is first rendered. Client-side transitions (edit ↔ preview) swap the panel content via HTMX posts.

### YAML Generation on Upload
- When a resume is submitted to `/resume/`, the view:
  1. Extracts text (from PDF or textarea) as today.
  2. Calls `WriterService.stream_yaml()` synchronously (collects the full iterator) and stores the resulting YAML string in the session under `shared_yaml`.
  3. Calls `RenderCVBuilder.render_html()` and stores the HTML in the session under `shared_html`.
  4. Returns the panel partial in Preview state.
- No streaming for the panel flow — generation completes before the response is sent.
- If YAML generation or HTML render fails, the panel returns to Upload state with an error message.

### New Session Keys
- `shared_yaml`: the full rendercv YAML string generated from the resume.
- `shared_html`: the rendered HTML string from rendercv.
- Existing `shared_resume` key (text + filename) is preserved.

### New Endpoints
- `POST /resume/` — extended to also generate YAML and HTML, store them in session, return panel partial in Preview state.
- `POST /resume/render/` — takes `yaml_content` from form, re-renders HTML via `RenderCVBuilder.render_html()`, updates `shared_html` in session, returns panel partial in Preview state.
- `POST /resume/build/` — takes `yaml_content` from form, calls `RenderCVBuilder.build_pdf()`, returns PDF as file attachment.
- These panel-level endpoints are distinct from the Writer tool's existing `/writer/build/` and `/writer/render/` endpoints, which remain unchanged.

### Warning on Resume Replacement
- The Upload state panel includes a confirmation step when a resume is already in session.
- An inline HTMX confirmation prompt (or JS `confirm()`) warns the user before submitting a new resume.
- On confirmation, the new resume replaces all session keys (`shared_resume`, `shared_yaml`, `shared_html`).

### Tool Page Changes
- Each tool's existing resume upload section is removed from its template.
- Each tool template extends the shared two-column base template.
- The panel is rendered server-side from session state on each page load.

### `shared/session.py` Changes
- Add `set_shared_yaml` / `get_shared_yaml` helpers.
- Add `set_shared_html` / `get_shared_html` helpers.
- Add `clear_shared_resume` to remove all three keys atomically.

### Landing Page
- A new minimal view (or `TemplateView`) at `/` renders a static marketing template.
- No session reads or writes.
- Contains: product headline, short description, tool sections (Analyzer, Coach, Compare, Writer), and a CTA button to `/home`.

## Testing Decisions

Good tests focus on observable behavior through the module's public interface — what comes out given what goes in — not on internal implementation details.

### Modules to Test

**`shared/session.py` (new helpers)**
- Unit tests: set/get/clear round-trips for all three session keys.

**`apps/home/views.py` (extended `submit_resume`, new `render_panel`, `build_pdf`)**
- Integration tests using Django's test client.
- Submit resume → session contains `shared_yaml` and `shared_html`; response is panel in Preview state.
- Submit resume with bad PDF → panel returns Upload state with error message.
- Submit resume when YAML generation fails (inject `FakeWriterService` that raises) → Upload state with error.
- `render_panel` POST with valid YAML → returns Preview state HTML.
- `build_pdf` POST with valid YAML → returns PDF bytes with correct `Content-Type`.
- Prior art: `apps/writer/tests/test_views.py` and `apps/analyzer/tests/test_views.py` for fake-injection pattern.

**Panel state rendering (via view responses)**
- No session → panel renders Upload state (contains upload form).
- Session with `shared_html` → panel renders Preview state (contains edit/download buttons).

**`WriterService` and `RenderCVBuilder`** — no changes needed; existing tests remain sufficient.

### What Not to Test
- The marketing landing page (static template, no logic).
- CSS layout details or JavaScript interactions.
- Internal HTMX swap mechanics.

## Out of Scope

- Mobile/responsive layout.
- The Resume Writer tool page (`/writer/`) is unchanged beyond adopting the shared panel layout.
- Authentication or user accounts.
- Persisting resumes or YAML to a database.
- Streaming YAML generation in the panel (synchronous background generation only).
- Per-tool "stale resume" banners (remain as-is in Coach and Compare until a future PRD).

## Further Notes

- The YAML generation in the panel flow reuses `WriterService` and `RenderCVBuilder` directly — no new AI logic is needed.
- Because YAML generation is synchronous, large resumes may cause a slow response on `/resume/` submit. A loading spinner on the submit button is desirable to manage perceived latency.
- The `/writer/` tool currently reads `shared_resume` from session for its own parse step. After this change, if `shared_yaml` is already in session, the Writer page could optionally pre-populate its YAML editor — but this is out of scope.
- `shared_html` stored in session may be large for complex resumes. If session size becomes a concern, storing only `shared_yaml` and re-rendering on each panel load is a viable alternative, but is not required by this PRD.
