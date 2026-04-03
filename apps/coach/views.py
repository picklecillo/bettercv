import dataclasses
import re

from django.http import HttpResponse, HttpResponseRedirect, JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST, require_GET

from apps.shared.pdf import PdfExtractionError, extract_text_from_pdf
from apps.shared import session as sess

from .coach_service import CoachParseError, WorkExperience, get_coach_service
from .yaml_utils import ExperienceNotFoundError, apply_experience_highlights


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def _process_assistant_message(content: str) -> dict:
    """Mirror the stream view's rewrite extraction for restoring conversation history."""
    from html import escape as html_escape
    rewrite_match = re.search(r'<rewrite>(.*?)</rewrite>', content, re.DOTALL | re.IGNORECASE)
    if rewrite_match:
        rewrite_text = rewrite_match.group(1).strip()
        display_content = re.sub(
            r'<rewrite>(.*?)</rewrite>', r'\1', content,
            flags=re.DOTALL | re.IGNORECASE,
        ).strip()
        rewrite_attr = html_escape(rewrite_text).replace('\n', '&#10;').replace('\r', '&#13;')
    else:
        display_content = content
        rewrite_attr = None
    return {"role": "assistant", "display_content": display_content, "rewrite_attr": rewrite_attr}


def _build_experiences_with_history(experiences: list[WorkExperience], conversations: dict) -> list[dict]:
    result = []
    for i, exp in enumerate(experiences):
        history = conversations.get(str(i), [])
        # Skip the first user message (hidden initial trigger sent by the chat view)
        raw_display = history[1:] if history and history[0]["role"] == "user" else history
        processed = [
            _process_assistant_message(m["content"]) if m["role"] == "assistant"
            else {"role": "user", "display_content": m["content"], "rewrite_attr": None}
            for m in raw_display
        ]
        result.append({
            "exp": exp,
            "index": i,
            "display_history": processed,
        })
    return result


def index(request):
    shared_store = sess.shared(request.session)
    coach_store = sess.coach(request.session)
    if coach_store.exists:
        experiences = [WorkExperience(**e) for e in coach_store.experiences]
        stale_resume = coach_store.is_stale(shared_store)
        experiences_with_history = _build_experiences_with_history(
            experiences, coach_store.conversations
        )
        return render(request, "coach/index.html", {
            **shared_store.panel_context(),
            "active_tool": "coach",
            "restore": True,
            "experiences_with_history": experiences_with_history,
            "cv_text": coach_store.cv_text,
            "stale_resume": stale_resume,
        })
    request.session.pop("coach", None)
    return render(request, "coach/index.html", {
        **shared_store.panel_context(),
        "active_tool": "coach",
    })


@require_POST
def reset(request):
    request.session.pop("coach", None)
    response = HttpResponse()
    response["HX-Redirect"] = "/coach/"
    return response


def workspace(request):
    coach_store = sess.coach(request.session)
    if not coach_store.exists:
        return HttpResponseRedirect("/coach/")
    shared_store = sess.shared(request.session)
    experiences = [WorkExperience(**e) for e in coach_store.experiences]
    stale_resume = coach_store.is_stale(shared_store)
    experiences_with_history = _build_experiences_with_history(
        experiences, coach_store.conversations
    )
    return render(request, "coach/split_screen.html", {
        **shared_store.panel_context(),
        "active_tool": "coach",
        "experiences_with_history": experiences_with_history,
        "cv_text": coach_store.cv_text,
        "stale_resume": stale_resume,
    })


@require_POST
def parse(request):
    if request.FILES.get("resume_pdf"):
        try:
            cv_text = extract_text_from_pdf(request.FILES["resume_pdf"])
        except PdfExtractionError as e:
            return _error(str(e))
    else:
        cv_text = request.POST.get("cv_text", "").strip()
        if not cv_text:
            return _error("Please provide your CV (text or PDF).")

    try:
        experiences = get_coach_service().parse_cv(cv_text)
    except CoachParseError as e:
        return _error(str(e))

    shared_store = sess.shared(request.session)
    coach_store = sess.coach(request.session)
    coach_store.initialize(
        cv_text=cv_text,
        experiences=[dataclasses.asdict(e) for e in experiences],
        resume_version=shared_store.resume_version,
    )

    experiences_with_history = _build_experiences_with_history(
        experiences, coach_store.conversations
    )
    return render(request, "coach/split_screen.html", {
        **shared_store.panel_context(),
        "active_tool": "coach",
        "cv_text": cv_text,
        "experiences_with_history": experiences_with_history,
        "stale_resume": False,
    })


@require_POST
def chat(request):
    coach_store = sess.coach(request.session)
    if not coach_store.exists:
        return _error("Session expired. Please re-upload your CV.")

    try:
        exp_index = int(request.POST.get("exp_index", ""))
        experience_data = coach_store.experiences[exp_index]
    except (ValueError, IndexError):
        return _error("Invalid experience selected.")

    experience = WorkExperience(**experience_data)
    is_followup = request.POST.get("is_followup") == "1"

    if is_followup:
        user_message = request.POST.get("user_message", "").strip()
        if not user_message:
            return _error("Please enter a message.")
    else:
        # Hidden prefilled first message — not shown in the UI
        user_message = experience.original_description

    nonce_key = sess.nonce(request.session).put({
        "exp_index": exp_index,
        "user_message": user_message,
    })

    sse_container = (
        f'<div id="sse-container-{nonce_key}"'
        f'     hx-ext="sse"'
        f'     sse-connect="/coach/stream/?key={nonce_key}"'
        f'     sse-close="done">'
        f'  <div class="stream-status">Thinking<span class="dots">...</span></div>'
        f'  <div id="stream-output-{nonce_key}"'
        f'       sse-swap="chunk"'
        f'       hx-swap="beforeend"></div>'
        f'  <div sse-swap="wrap"'
        f'       hx-target="#sse-container-{nonce_key}"'
        f'       hx-swap="outerHTML"></div>'
        f'</div>'
    )

    if is_followup:
        safe_msg = escape(user_message).replace("\n", "<br>")
        user_bubble = f'<div class="chat-msg user-msg"><div class="msg-body">{safe_msg}</div></div>'
        return HttpResponse(user_bubble + sse_container, content_type="text/html")

    return HttpResponse(sse_container, content_type="text/html")


def stream(request):
    key = request.GET.get("key", "")
    nonce_data = sess.nonce(request.session).pop(key)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    coach_store = sess.coach(request.session)
    if not coach_store.exists:
        return HttpResponse("Coach session expired. Please re-upload your CV.", status=400)

    exp_index = nonce_data["exp_index"]
    user_message = nonce_data["user_message"]
    experience = WorkExperience(**coach_store.experiences[exp_index])

    existing_history = coach_store.get_conversation(exp_index)
    messages_to_send = existing_history + [{"role": "user", "content": user_message}]

    def event_stream():
        accumulated = []
        errored = False
        try:
            for chunk in get_coach_service().stream_reply(experience, messages_to_send):
                accumulated.append(chunk)
                safe = escape(chunk).replace("\n", "<br>")
                yield f"event: chunk\ndata: <span>{safe}</span>\n\n"
        except Exception as e:
            errored = True
            safe_msg = escape(str(e))
            yield f"event: chunk\ndata: <div class='result-error'>Error: {safe_msg}</div>\n\n"

        if not errored and accumulated:
            assistant_reply = "".join(accumulated)
            final_messages = messages_to_send + [{"role": "assistant", "content": assistant_reply}]
            coach_store.save_conversation(exp_index, final_messages)

            # Extract <rewrite> block; store as data attribute, strip from visible text
            rewrite_match = re.search(r'<rewrite>(.*?)</rewrite>', assistant_reply, re.DOTALL | re.IGNORECASE)
            if rewrite_match:
                rewrite_text = rewrite_match.group(1).strip()
                clean_reply = re.sub(
                    r'<rewrite>(.*?)</rewrite>', r'\1', assistant_reply,
                    flags=re.DOTALL | re.IGNORECASE,
                ).strip()
            else:
                rewrite_text = None
                clean_reply = assistant_reply

            safe_full = escape(clean_reply).replace("\n", "<br>")
            if rewrite_text:
                rewrite_attr_val = escape(rewrite_text).replace('\n', '&#10;').replace('\r', '&#13;')
                rewrite_attr = f' data-rewrite="{rewrite_attr_val}"'
            else:
                rewrite_attr = ''
            wrapped = (
                f'<div class="chat-msg assistant-msg"{rewrite_attr} id="msg-{key}">'
                f'<div class="msg-body">{safe_full}</div>'
                f'</div>'
            )
            wrapped_lines = "\n".join(f"data: {line}" for line in wrapped.splitlines())
            yield f"event: wrap\n{wrapped_lines}\n\n"

        yield "event: done\ndata: \n\n"

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@require_POST
def apply(request):
    coach_store = sess.coach(request.session)
    if not coach_store.exists:
        return JsonResponse({"ok": False, "error": "Session expired. Please re-upload your CV."}, status=400)

    try:
        exp_index = int(request.POST.get("exp_index", ""))
        experience_data = coach_store.experiences[exp_index]
    except (ValueError, IndexError):
        return JsonResponse({"ok": False, "error": "Invalid experience selected."}, status=400)

    rewrite_text = request.POST.get("rewrite_text", "").strip()
    if not rewrite_text:
        return JsonResponse({"ok": False, "error": "No rewrite text provided."}, status=400)

    shared_store = sess.shared(request.session)
    shared_yaml = shared_store.yaml
    if not shared_yaml:
        return JsonResponse(
            {"ok": False, "error": "No resume YAML found. Generate your resume in the Writer tab first."},
            status=409,
        )

    experience = WorkExperience(**experience_data)

    try:
        updated_yaml = apply_experience_highlights(
            shared_yaml,
            company=experience.company,
            position=experience.title,
            rewrite_text=rewrite_text,
        )
    except ExperienceNotFoundError:
        return JsonResponse(
            {
                "ok": False,
                "error": f"Could not find '{experience.title}' at '{experience.company}' in the resume YAML.",
            },
            status=404,
        )

    shared_store.set_yaml(updated_yaml)
    shared_store.invalidate_html()
    request.session.save()

    return JsonResponse({"ok": True})


def conversation(request, exp_index: int):
    coach_store = sess.coach(request.session)
    if not coach_store.exists:
        return _error("Session expired. Please re-upload your CV.")

    try:
        experience = WorkExperience(**coach_store.experiences[exp_index])
    except IndexError:
        return _error("Invalid experience.")

    history = coach_store.get_conversation(exp_index)
    return render(request, "coach/conversation.html", {
        "experience": experience,
        "exp_index": exp_index,
        "history": history,
    })
