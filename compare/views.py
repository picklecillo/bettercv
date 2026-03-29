import uuid

from django.http import HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from analyzer.pdf import PdfExtractionError, extract_text_from_pdf
from .compare_service import CompareMetadataError, get_compare_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def index(request):
    request.session.pop("compare", None)
    return render(request, "compare/index.html")


@require_POST
def parse_resume(request):
    if request.FILES.get("resume_pdf"):
        try:
            resume_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
        except Exception as e:
            return _error(str(e))
    else:
        resume_text = request.POST.get("resume_text", "").strip()
        if not resume_text:
            return _error("Please provide your resume (text or PDF).")

    try:
        request.session["compare"] = {
            "resume_text": resume_text,
            "jds": {},
        }
    except Exception as e:
        return _error(str(e))

    try:
        return render(request, "compare/workspace.html", {"resume_text": resume_text})
    except Exception as e:
        return _error(str(e))


@require_POST
def add_jd(request):
    compare = request.session.get("compare")
    if not compare:
        return _error("Session expired. Please re-upload your resume.")

    jd_text = request.POST.get("jd_text", "").strip()
    if not jd_text:
        return _error("Please provide a job description.")

    if len(compare["jds"]) >= 10:
        return _error("Maximum of 10 job descriptions reached.")

    jd_id = str(uuid.uuid4())
    nonce = str(uuid.uuid4())

    compare["jds"][jd_id] = {"jd_text": jd_text, "analysis": None, "metadata": None}
    request.session.modified = True

    jd_num = len(compare["jds"])

    request.session[nonce] = {
        "jd_id": jd_id,
        "jd_num": jd_num,
        "resume_text": compare["resume_text"],
        "jd_text": jd_text,
    }
    request.session.modified = True

    # Primary response: <tr> into #summary-tbody.
    # HTMX wraps primary content in <template class="internal-htmx-wrapper"> before
    # parsing, which preserves <tr> elements. insertNodesBefore then inserts the <tr>
    # directly into <tbody> — this is the only reliable path for table rows in HTMX 2.
    summary_row = (
        f'<tr id="summary-row-{jd_id}" data-score-high="-1">'
        f'  <td>{jd_num}</td>'
        f'  <td>—</td>'
        f'  <td>—</td>'
        f'  <td><span class="status-analyzing">Analyzing…</span></td>'
        f'  <td></td>'
        f'</tr>'
    )

    # OOB: analysis card into #jd-cards. div-into-div OOB works because <div> is not
    # stripped when HTMX parses the response fragment.
    # hx-ext="sse", sse-connect, and sse-close live on the outer card div so that the
    # EventSource is not orphaned when the wrap event replaces #sse-wrap-{jd_id}.
    # Without this, the done event can't close the connection (sse-close is gone),
    # the first card's EventSource keeps reconnecting, and the second card's SSE
    # extension is corrupted.
    card_oob = (
        f'<div hx-swap-oob="beforeend:#jd-cards">'
        f'  <div class="analysis-card" id="card-{jd_id}"'
        f'       hx-ext="sse"'
        f'       sse-connect="/compare/stream/?key={nonce}"'
        f'       sse-close="done">'
        f'    <div class="card-top-bar streaming"></div>'
        f'    <div class="card-header">'
        f'      <span class="card-title">Job {jd_num}</span>'
        f'    </div>'
        f'    <div id="sse-wrap-{jd_id}">'
        f'      <div class="stream-status">Analyzing<span class="dots">...</span></div>'
        f'      <div id="stream-out-{jd_id}" sse-swap="chunk" hx-swap="beforeend" class="stream-output"></div>'
        f'      <div sse-swap="wrap" hx-target="#sse-wrap-{jd_id}" hx-swap="outerHTML"></div>'
        f'      <div sse-swap="metadata" hx-target="#summary-row-{jd_id}" hx-swap="outerHTML"></div>'
        f'    </div>'
        f'  </div>'
        f'</div>'
    )

    return HttpResponse(summary_row + card_oob, content_type="text/html")


@require_POST
def remove_jd(request):
    compare = request.session.get("compare")
    if not compare:
        return _error("Session expired. Please re-upload your resume.")

    jd_id = request.POST.get("jd_id", "")
    if jd_id not in compare["jds"]:
        return _error("Unknown job description.", status=400)

    del compare["jds"][jd_id]
    request.session.modified = True

    # Primary swap (hx-target="#summary-row-{jd_id}" hx-swap="delete") removes the row.
    # OOB delete removes the analysis card.
    card_oob = f'<div id="card-{jd_id}" hx-swap-oob="delete"></div>'
    return HttpResponse(card_oob, content_type="text/html")


def stream(request):
    key = request.GET.get("key", "")
    nonce_data = request.session.pop(key, None)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    request.session.modified = True

    compare = request.session.get("compare")
    if not compare:
        return HttpResponse("Compare session expired. Please re-upload your resume.", status=400)

    jd_id = nonce_data["jd_id"]
    jd_num = nonce_data["jd_num"]
    resume_text = nonce_data["resume_text"]
    jd_text = nonce_data["jd_text"]

    def event_stream():
        import markdown as md
        accumulated = []
        errored = False

        try:
            for chunk in get_compare_service().stream_analysis(resume_text, jd_text):
                accumulated.append(chunk)
                safe = escape(chunk).replace("\n", "<br>")
                yield f"event: chunk\ndata: <span>{safe}</span>\n\n"
        except Exception as e:
            errored = True
            safe_msg = escape(str(e))
            yield f"event: chunk\ndata: <div class='result-error'>Error: {safe_msg}</div>\n\n"

        if not errored and accumulated:
            analysis_text = "".join(accumulated)

            # Commit analysis to session
            compare["jds"][jd_id]["analysis"] = analysis_text
            request.session.modified = True

            # Extract metadata
            metadata_dict = None
            score_high_val = -1
            try:
                meta = get_compare_service().extract_metadata(analysis_text, jd_text)
                metadata_dict = {
                    "company": meta.company,
                    "title": meta.title,
                    "score_low": meta.score_low,
                    "score_high": meta.score_high,
                }
                score_high_val = meta.score_high
                compare["jds"][jd_id]["metadata"] = metadata_dict
                label = f"{escape(meta.company)} · {escape(meta.title)}"
                score = f"{meta.score_low}–{meta.score_high} / 100"
            except CompareMetadataError:
                label = "—"
                score = "—"

            request.session.save()

            # metadata event: update summary row BEFORE wrap removes the listener
            remove_btn = (
                f'<button class="remove-btn" '
                f'hx-post="/compare/remove-jd/" '
                f'hx-vals=\'{{"jd_id": "{jd_id}"}}\' '
                f'hx-include="[name=csrfmiddlewaretoken]" '
                f'hx-target="#summary-row-{jd_id}" '
                f'hx-swap="delete" '
                f'hx-confirm="Remove this analysis?">'
                f'Remove</button>'
            )
            row_html = (
                f'<tr id="summary-row-{jd_id}" data-score-high="{score_high_val}">'
                f'<td>{jd_num}</td>'
                f'<td>{escape(label)}</td>'
                f'<td>'
                f'<span class="score-badge">{escape(score)}</span>'
                f'<span class="best-star" aria-label="Best score">★</span>'
                f'</td>'
                f'<td>Done</td>'
                f'<td>{remove_btn}</td>'
                f'</tr>'
            )
            row_lines = "\n".join(f"data: {line}" for line in row_html.splitlines())
            yield f"event: metadata\n{row_lines}\n\n"

            # wrap event: replace streaming container with rendered markdown
            # (this removes the sse-swap listeners, so metadata must come first)
            rendered = md.markdown(analysis_text, extensions=["tables"])
            wrap_html = f'<div class="analysis-result">{rendered}</div>'
            wrap_lines = "\n".join(f"data: {line}" for line in wrap_html.splitlines())
            yield f"event: wrap\n{wrap_lines}\n\n"

        yield "event: done\ndata: \n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
