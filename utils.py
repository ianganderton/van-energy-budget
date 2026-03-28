import time


class OpenAIExtractionError(RuntimeError):
    """Error raised when the OpenAI extraction path fails."""

    def __init__(self, message, raw_response_text=""):
        super().__init__(message)
        self.raw_response_text = raw_response_text or ""


def log_timing(stage, start_time, **details):
    """Print a simple elapsed-time log line for request instrumentation."""
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    detail_parts = [f"{key}={value}" for key, value in details.items()]
    detail_text = f" | {' '.join(detail_parts)}" if detail_parts else ""
    print(f"TIMING: {stage} | elapsed_ms={elapsed_ms:.1f}{detail_text}")


def extract_response_text(response):
    """Read plain text from a Responses API result with fallback paths."""
    output_text = getattr(response, "output_text", "") or ""
    if output_text:
        return output_text.strip()

    output_items = getattr(response, "output", []) or []
    for item in output_items:
        content_items = getattr(item, "content", []) or []
        for content_item in content_items:
            text = getattr(content_item, "text", "") or ""
            if text:
                return text.strip()

        item_text = getattr(item, "text", "") or ""
        if item_text:
            return item_text.strip()

    return ""


def serialize_response_debug(response):
    """Serialize the response for terminal logging and UI error visibility."""
    if response is None:
        return ""

    try:
        return response.model_dump_json(indent=2)
    except Exception:
        return str(response)
