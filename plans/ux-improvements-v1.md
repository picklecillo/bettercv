# UX Improvements v1

Covers two features: Compare JD table enhancements and Resume Coach workspace redesign.

---

## Feature A: Compare Table — Clickable Rows

### Goal
Each table row in the JD summary scrolls to its corresponding analysis card when clicked.

### Context
- Table rows have `id="summary-row-{jd_id}"`, analysis cards have `id="card-{jd_id}"`
- Rows are inserted via HTMX (`hx-swap="beforeend"` into `#summary-tbody`) and later replaced by the `metadata` SSE event with full row HTML
- The remove button already lives inside the row; clicks on it must not trigger the scroll

### Implementation

**workspace.html** — add a delegated click listener on `#summary-tbody`:
```js
document.getElementById('summary-tbody').addEventListener('click', e => {
  const row = e.target.closest('tr[id^="summary-row-"]');
  if (!row || e.target.closest('button')) return; // ignore remove button clicks
  const jdId = row.id.replace('summary-row-', '');
  document.getElementById('card-' + jdId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
});
```

Add visual affordance to rows (cursor, hover state):
```css
#summary-tbody tr { cursor: pointer; }
#summary-tbody tr:hover td { background: var(--surface-hover, #f5f5f5); }
```

No backend changes needed.

---

## Feature B: Compare Table — Star on Best Score

### Goal
Show a star icon (⭐ or SVG) on the right of the ATS score cell for any row whose `score_high` equals the highest `score_high` across all currently rendered rows. All tied rows get a star.

### Context
- Rows arrive incrementally via SSE `metadata` events (server emits `outerHTML` of the whole `<tr>`)
- `score_high` is rendered inside the score badge as `{score_low}–{score_high} / 100`
- After every metadata swap we must re-evaluate all rows

### Implementation

**Star injection in server-rendered row HTML** (`compare/views.py`, `_summary_row_html()` helper):
- Keep the star markup always present but hidden: `<span class="best-star" aria-label="Best score" style="visibility:hidden">★</span>`
- Place it immediately after the score badge inside the score `<td>`

**Client-side re-evaluation** — call `updateBestStar()` after every metadata SSE swap:
```js
function updateBestStar() {
  const rows = document.querySelectorAll('#summary-tbody tr[id^="summary-row-"]');
  let best = -1;
  rows.forEach(row => {
    const high = parseInt(row.dataset.scoreHigh ?? '-1', 10);
    if (high > best) best = high;
  });
  rows.forEach(row => {
    const high = parseInt(row.dataset.scoreHigh ?? '-1', 10);
    const star = row.querySelector('.best-star');
    if (star) star.style.visibility = (best >= 0 && high === best) ? 'visible' : 'hidden';
  });
}
```

Store `score_high` as a `data-score-high` attribute on the `<tr>` (server-rendered):
```html
<tr id="summary-row-{jd_id}" data-score-high="{score_high}">
```

Hook the re-evaluation: HTMX fires `htmx:afterSwap` on the target element after every swap. Listen on `document`:
```js
document.addEventListener('htmx:afterSwap', e => {
  if (e.target.id?.startsWith('summary-row-')) updateBestStar();
});
```

No backend schema changes. `score_low`/`score_high` already come from `metadata`.

---

## Feature C: Resume Coach — Workspace Redesign

### Current layout
```
Left col:  raw CV text
Right col: WE button list (top) + single shared chat (bottom)
```

### New layout
```
Left col:  WE button list (replaces raw CV text)
Right col: [selected WE original description]
           [updated description section — appears after first AI rewrite]
           [chat — one per WE, independent history]
```

---

### C1 — Move WE list to left column; remove CV transcript

**split_screen.html changes:**
- Left panel: replace `<div class="cv-text">{{ cv_text }}</div>` with the experience button list (same markup already in the right column)
- Right panel: remove the experience button list from the top; the right panel now holds only the coaching area

The WE buttons remain `hx-post="/coach/chat/"` etc. — no backend change.

---

### C2 — Original description at top of right pane

When a WE is selected, show a read-only block above the chat area:
```html
<div id="we-description-panel">
  <div id="we-original-section" class="we-section" style="display:none">
    <div class="we-section-label">Current description</div>
    <div id="we-original-body" class="we-description-body"></div>
  </div>
  <!-- C3: updated section injected here -->
  <div id="chat-area">...</div>
</div>
```

When a WE button is clicked, JS populates `#we-original-body` from the button's `data-description` attribute and makes the section visible.

**Server change:** each WE button gets `data-description="{{ exp.original_description|escapejs }}"` attribute (already available from the template context).

---

### C3 — Updated description section

**Structured AI output format:**

Update the system prompt in `coach_service.py` to instruct the model: whenever it proposes a rewrite, wrap it in `<rewrite>` tags:

```
When you propose a rewritten work experience description, output it wrapped in
<rewrite> ... </rewrite> tags so it can be extracted and displayed separately.
```

**Client-side extraction:**

After the SSE `wrap` event fires (assistant message is now fully in the DOM), scan the new `.chat-msg.assistant-msg` for a `<rewrite>` block:
```js
function extractRewrite(msgEl) {
  const raw = msgEl.querySelector('.msg-body').innerHTML;
  const match = raw.match(/<rewrite>([\s\S]*?)<\/rewrite>/i);
  if (!match) return null;
  // strip the <rewrite> tags from the visible chat bubble
  msgEl.querySelector('.msg-body').innerHTML = raw.replace(/<rewrite>[\s\S]*?<\/rewrite>/i, '').trim();
  return match[1].trim();
}
```

Show the updated description section (initially hidden), and always overwrite with the latest rewrite:
```js
const rewrite = extractRewrite(newMsgEl);
if (rewrite) {
  document.getElementById('we-updated-section').style.display = 'block';
  document.getElementById('we-updated-body').innerHTML = rewrite;
}
```

**HTML for updated section** (inserted between original section and chat area):
```html
<div id="we-updated-section" class="we-section" style="display:none">
  <div class="we-section-label">
    Updated description
    <button class="copy-btn" onclick="copyUpdated()">Copy</button>
  </div>
  <div id="we-updated-body" class="we-description-body"></div>
</div>
```

```js
function copyUpdated() {
  navigator.clipboard.writeText(document.getElementById('we-updated-body').innerText);
}
```

**Remove the per-message copy button** from the `wrap` event HTML in `views.py` — copying now happens only via the updated description section button.

---

### C4 — Per-WE independent chat history

**Goal:** each WE maintains its own chat DOM. Switching WEs hides/shows the correct chat container. The backend already stores `conversations[exp_index]` in session, so the history is preserved on reload; frontend-only approach is fine for this iteration.

**New chat container structure** — render one `<div>` per experience on page load:
```html
{% for exp in experiences %}
<div id="chat-pane-{{ forloop.counter0 }}"
     class="chat-pane"
     style="display: {% if forloop.first %}block{% else %}none{% endif %}">
  <div id="chat-transcript-{{ forloop.counter0 }}" class="chat-transcript"></div>
  <div id="chat-input-{{ forloop.counter0 }}" class="chat-input-area" style="display:none">
    <!-- existing send form, hx-vals includes exp_index -->
  </div>
</div>
{% endfor %}
```

**WE button click:** instead of swapping `#chat-transcript`, switch visibility of panes:
```js
function selectExp(idx) {
  document.querySelectorAll('.chat-pane').forEach(p => p.style.display = 'none');
  document.getElementById('chat-pane-' + idx).style.display = 'block';
}
```

**HTMX targets:** update buttons so that `hx-target` points to `#chat-transcript-{idx}` and `hx-swap="beforeend"` (same as current, just scoped per-pane).

**Updated description and original description:** reset/re-populate from the clicked WE's data on every button click (they are shared UI elements but re-populated instantly, which is fine since they are not part of chat history).

**Conversation loading** (`/coach/chat/` view): no change needed — it already targets the specific `exp_index`, appends messages, and the stream SSE container is injected into the correct transcript div.

---

## Phased delivery

| Phase | Scope |
|-------|-------|
| 1 | Feature A (clickable rows) + Feature B (star icon) — pure frontend, no backend |
| 2 | Feature C1 + C2 — layout change + original description display |
| 3 | Feature C3 — structured AI rewrite output + updated description section + new copy button |
| 4 | Feature C4 — per-WE independent chat panes |

Each phase is independently shippable and testable.

---

## Files touched

| File | Changes |
|------|---------|
| `compare/templates/compare/workspace.html` | Clickable rows JS/CSS, star markup, `data-score-high` attr, `updateBestStar()` JS |
| `compare/views.py` | Add `data-score-high` and `.best-star` to `_summary_row_html()` |
| `coach/templates/coach/split_screen.html` | Move WE list to left col, add `data-description` to WE buttons, add `#we-description-panel`, per-WE chat panes, `selectExp()` JS |
| `coach/coach_service.py` | Update system prompt to require `<rewrite>` tags around rewrites |
| `coach/views.py` | Remove per-message copy button from wrap event HTML |
