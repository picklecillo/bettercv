import anthropic
from django.conf import settings


MODEL = "claude-sonnet-4-20250514"


class ClaudeServiceError(Exception):
    def __init__(self, message: str, status: int) -> None:
        super().__init__(message)
        self.message = message
        self.status = status


_ERROR_MESSAGES: dict[str, tuple[str, int]] = {
    "authentication_error":  ("Invalid API key. Check your ANTHROPIC_API_KEY.", 502),
    "permission_error":      ("Your API key doesn't have permission to use this model.", 502),
    "invalid_request_error": ("Bad request sent to AI API.", 502),
    "not_found_error":       ("AI model not found.", 502),
    "rate_limit_error":      ("Rate limit hit. Please wait a moment and try again.", 502),
    "api_error":             ("AI API internal error. Please try again.", 502),
    "overloaded_error":      ("AI is currently overloaded. Please try again shortly.", 502),
}


def translate_api_error(e: anthropic.APIStatusError) -> ClaudeServiceError:
    if "credit balance is too low" in str(e):
        return ClaudeServiceError(
            "Your AI API credit balance is too low. "
            "Please add credits at console.anthropic.com.",
            402,
        )
    error_type = (e.body or {}).get("error", {}).get("type", "")
    msg, status = _ERROR_MESSAGES.get(error_type, (str(e), 502))
    return ClaudeServiceError(msg, status)


def translate_connection_error(e: anthropic.APIConnectionError) -> ClaudeServiceError:
    return ClaudeServiceError(
        "Could not reach the AI API. Check your internet connection.", 503
    )


def make_client() -> anthropic.Anthropic:
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
