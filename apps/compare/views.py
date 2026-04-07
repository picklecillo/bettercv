import uuid
from collections.abc import Generator

import markdown as md
from django.http import HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared import session as sess
from apps.shared.decorators import htmx_login_required
from apps.shared.sse import SSEEvent, SseStream, no_credits_response

from .compare_service import CompareMetadataError, get_compare_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def _build_jds_for_restore(compare_store) -> list[dict]:
    result = []
    for i, (jd_id, jd) in enumerate(compare_store.all_jds(), start=1):
        analysis_html = None
        if jd.get("analysis"):
            analysis_html = md.markdown(jd["analysis"], extensions=["tables"])
        result.append({
            "jd_id": jd_id,
            "jd_num": i,
            "analysis_html": analysis_html,
            "metadata": jd.get("metadata"),
            "jd_text": jd["jd_text"],
        })
    return result


@htmx_login_required
def index(request):
    shared_store = sess.shared(request.session)
    compare_store = sess.compare(request.session)
    if compare_store.has_jds:
        stale_resume = compare_store.is_stale(shared_store)
        return render(request, "compare/index.html", {
            **shared_store.panel_context(),
            "active_tool": "compare",
            "restore": True,
            "stale_resume": stale_resume,
            "jds_for_restore": _build_jds_for_restore(compare_store),
        })
    request.session.pop("compare", None)
    return render(request, "compare/index.html", {
        **shared_store.panel_context(),
        "active_tool": "compare",
    })


@require_POST
def reset(request):
    request.session.pop("compare", None)
    response = HttpResponse()
    response["HX-Redirect"] = "/compare/"
    return response


def workspace(request):
    compare_store = sess.compare(request.session)
    if not compare_store.is_initialized:
        return HttpResponseRedirect("/compare/")
    shared_store = sess.shared(request.session)
    stale_resume = compare_store.is_stale(shared_store)
    return render(request, "compare/workspace.html", {
        **shared_store.panel_context(),
        "active_tool": "compare",
        "resume_text": compare_store.resume_text,
        "stale_resume": stale_resume,
    })


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
        shared_store = sess.shared(request.session)
        compare_store = sess.compare(request.session)
        compare_store.initialize(
            resume_text=resume_text,
            resume_version=shared_store.resume_version,
        )
    except Exception as e:
        return _error(str(e))

    try:
        return render(request, "compare/workspace.html", {
            **shared_store.panel_context(),
            "active_tool": "compare",
            "resume_text": resume_text,
            "stale_resume": False,
        })
    except Exception as e:
        return _error(str(e))


@require_POST
def add_jd(request):
    compare_store = sess.compare(request.session)
    if not compare_store.is_initialized:
        return _error("Session expired. Please re-upload your resume.")

    jd_text = request.POST.get("jd_text", "").strip()
    if not jd_text:
        return _error("Please provide a job description.")

    if compare_store.jd_count() >= 10:
        return _error("Maximum of 10 job descriptions reached.")

    jd_id = str(uuid.uuid4())
    compare_store.add_jd(jd_id, jd_text)
    jd_num = compare_store.jd_count()

    nonce_key = sess.nonce(request.session).put({
        "jd_id": jd_id,
        "jd_num": jd_num,
        "resume_text": compare_store.resume_text,
        "jd_text": jd_text,
    })

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
        f'       sse-connect="/compare/stream/?key={nonce_key}"'
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
    compare_store = sess.compare(request.session)
    if not compare_store.is_initialized:
        return _error("Session expired. Please re-upload your resume.")

    jd_id = request.POST.get("jd_id", "")
    if not compare_store.get_jd(jd_id):
        return _error("Unknown job description.", status=400)

    compare = request.session.get("compare")
    del compare["jds"][jd_id]
    if hasattr(request.session, "modified"):
        request.session.modified = True

    # Primary swap (hx-target="#summary-row-{jd_id}" hx-swap="delete") removes the row.
    # OOB delete removes the analysis card.
    card_oob = f'<div id="card-{jd_id}" hx-swap-oob="delete"></div>'
    return HttpResponse(card_oob, content_type="text/html")


@htmx_login_required
def stream(request):
    key = request.GET.get("key", "")
    nonce_data = sess.nonce(request.session).pop(key)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    from apps.accounts.credits import deduct_credit
    if not deduct_credit(request.user, 1, 'JD comparison'):
        return no_credits_response()

    compare_store = sess.compare(request.session)
    if not compare_store.is_initialized:
        return HttpResponse("Compare session expired. Please re-upload your resume.", status=400)

    jd_id = nonce_data["jd_id"]
    jd_num = nonce_data["jd_num"]
    resume_text = nonce_data["resume_text"]
    jd_text = nonce_data["jd_text"]

    def finalizer(accumulated: str | None) -> Generator[SSEEvent, None, None]:
        if accumulated is None:
            return

        metadata_dict = None
        score_high_val = -1
        try:
            meta = get_compare_service().extract_metadata(accumulated, jd_text)
            metadata_dict = {
                "company": meta.company,
                "title": meta.title,
                "score_low": meta.score_low,
                "score_high": meta.score_high,
            }
            score_high_val = meta.score_high
            label = f"{escape(meta.company)} · {escape(meta.title)}"
            score = f"{meta.score_low}–{meta.score_high} / 100"
        except CompareMetadataError:
            label = "—"
            score = "—"

        compare_store.set_jd_result(jd_id, accumulated, metadata_dict)

        # metadata MUST be yielded before wrap — wrap removes the sse-swap listeners
        # that receive metadata. Ordering is structurally enforced by yield order.
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
        yield SSEEvent("metadata", row_html)

        rendered = md.markdown(accumulated, extensions=["tables"])
        yield SSEEvent("wrap", f'<div class="analysis-result">{rendered}</div>')

    return SseStream(
        source=get_compare_service().stream_analysis(resume_text, jd_text),
        finalizer=finalizer,
    ).response()


@require_POST
def reanalyze(request, jd_id: str):
    compare_store = sess.compare(request.session)
    if not compare_store.is_initialized:
        return _error("Session expired. Please re-upload your resume.")

    jd = compare_store.get_jd(jd_id)
    if not jd:
        return _error("Unknown job description.", status=400)

    jd_text = jd["jd_text"]
    jd_num = list(compare_store.all_jds()).index((jd_id, jd)) + 1

    nonce_key = sess.nonce(request.session).put({
        "jd_id": jd_id,
        "jd_num": jd_num,
        "resume_text": compare_store.resume_text,
        "jd_text": jd_text,
    })

    card_html = (
        f'<div class="analysis-card" id="card-{jd_id}"'
        f'     hx-ext="sse"'
        f'     sse-connect="/compare/stream/?key={nonce_key}"'
        f'     sse-close="done">'
        f'  <div class="card-top-bar streaming"></div>'
        f'  <div class="card-header">'
        f'    <span class="card-title">Job {jd_num}</span>'
        f'  </div>'
        f'  <div id="sse-wrap-{jd_id}">'
        f'    <div class="stream-status">Analyzing<span class="dots">...</span></div>'
        f'    <div id="stream-out-{jd_id}" sse-swap="chunk" hx-swap="beforeend" class="stream-output"></div>'
        f'    <div sse-swap="wrap" hx-target="#sse-wrap-{jd_id}" hx-swap="outerHTML"></div>'
        f'    <div sse-swap="metadata" hx-target="#summary-row-{jd_id}" hx-swap="outerHTML"></div>'
        f'  </div>'
        f'</div>'
    )
    return HttpResponse(card_html, content_type="text/html")
