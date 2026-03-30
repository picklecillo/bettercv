import dataclasses
import re
import uuid

from django.http import HttpResponse, HttpResponseRedirect, StreamingHttpResponse
from django.shortcuts import render
from django.utils.html import escape
from django.views.decorators.http import require_POST, require_GET

from shared.pdf import PdfExtractionError, extract_text_from_pdf
from shared.session import get_resume_version, get_shared_resume
from .coach_service import CoachParseError, WorkExperience, get_coach_service


def _error(message: str, status: int = 400) -> HttpResponse:
    return HttpResponse(
        f'<div class="result-error">{escape(message)}</div>',
        status=status,
        content_type="text/html",
    )


def _experiences_from_session(session) -> list[WorkExperience] | None:
    coach = session.get("coach")
    if not coach:
        return None
    return [WorkExperience(**e) for e in coach["experiences"]]


def _is_stale(session, coach_session: dict) -> bool:
    shared_version = get_resume_version(session)
    if shared_version is None:
        return False
    tool_version = coach_session.get("resume_version")
    if tool_version is None:
        return False
    return shared_version > tool_version


def index(request):
    request.session.pop("coach", None)
    shared = get_shared_resume(request.session)
    return render(request, "coach/index.html", {"shared_resume": shared})


def workspace(request):
    coach = request.session.get("coach")
    if not coach:
        return HttpResponseRedirect("/coach/")
    experiences = [WorkExperience(**e) for e in coach["experiences"]]
    shared = get_shared_resume(request.session)
    stale_resume = _is_stale(request.session, coach)
    return render(request, "coach/split_screen.html", {
        "experiences": experiences,
        "cv_text": coach["cv_text"],
        "stale_resume": stale_resume,
        "shared_resume": shared,
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

    existing_conversations = (request.session.get("coach") or {}).get("conversations", {})
    resume_version = get_resume_version(request.session)
    request.session["coach"] = {
        "cv_text": cv_text,
        "experiences": [dataclasses.asdict(e) for e in experiences],
        "conversations": existing_conversations,
        "resume_version": resume_version,
    }

    shared = get_shared_resume(request.session)
    return render(request, "coach/split_screen.html", {
        "cv_text": cv_text,
        "experiences": experiences,
        "stale_resume": False,
        "shared_resume": shared,
    })


@require_POST
def chat(request):
    coach = request.session.get("coach")
    if not coach:
        return _error("Session expired. Please re-upload your CV.")

    try:
        exp_index = int(request.POST.get("exp_index", ""))
        experience_data = coach["experiences"][exp_index]
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

    nonce = str(uuid.uuid4())
    request.session[nonce] = {
        "exp_index": exp_index,
        "user_message": user_message,
    }
    request.session.modified = True

    sse_container = (
        f'<div id="sse-container-{nonce}"'
        f'     hx-ext="sse"'
        f'     sse-connect="/coach/stream/?key={nonce}"'
        f'     sse-close="done">'
        f'  <div class="stream-status">Thinking<span class="dots">...</span></div>'
        f'  <div id="stream-output-{nonce}"'
        f'       sse-swap="chunk"'
        f'       hx-swap="beforeend"></div>'
        f'  <div sse-swap="wrap"'
        f'       hx-target="#sse-container-{nonce}"'
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
    nonce_data = request.session.pop(key, None)
    if not nonce_data:
        return HttpResponse("Session expired. Please try again.", status=400)

    request.session.modified = True

    coach = request.session.get("coach")
    if not coach:
        return HttpResponse("Coach session expired. Please re-upload your CV.", status=400)

    exp_index = nonce_data["exp_index"]
    user_message = nonce_data["user_message"]
    experience = WorkExperience(**coach["experiences"][exp_index])

    existing_history = coach["conversations"].get(str(exp_index), [])
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
            coach["conversations"][str(exp_index)] = messages_to_send + [
                {"role": "assistant", "content": assistant_reply}
            ]
            request.session.modified = True
            request.session.save()

            # Extract <rewrite> block; store as data attribute, strip from visible text
            rewrite_match = re.search(r'<rewrite>(.*?)</rewrite>', assistant_reply, re.DOTALL | re.IGNORECASE)
            if rewrite_match:
                rewrite_text = rewrite_match.group(1).strip()
                # Strip only the tags; keep the content visible in the chat bubble
                clean_reply = re.sub(r'<rewrite>(.*?)</rewrite>', r'\1', assistant_reply, flags=re.DOTALL | re.IGNORECASE).strip()
            else:
                rewrite_text = None
                clean_reply = assistant_reply

            safe_full = escape(clean_reply).replace("\n", "<br>")
            if rewrite_text:
                # Encode newlines so they survive the HTML attribute
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


def conversation(request, exp_index: int):
    coach = request.session.get("coach")
    if not coach:
        return _error("Session expired. Please re-upload your CV.")

    try:
        experience = WorkExperience(**coach["experiences"][exp_index])
    except IndexError:
        return _error("Invalid experience.")

    history = coach["conversations"].get(str(exp_index), [])
    return render(request, "coach/conversation.html", {
        "experience": experience,
        "exp_index": exp_index,
        "history": history,
    })
