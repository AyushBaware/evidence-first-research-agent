import json
import re
import time

from openai import (APIConnectionError, APITimeoutError, BadRequestError,
                    InternalServerError, OpenAI, RateLimitError)
from pydantic import BaseModel, ValidationError
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app import config
from app.tracing import Tracer


class LLMError(Exception):
    """Raised when the provider fails or never returns valid JSON."""


# max_retries=0: the SDK must not retry silently; tenacity below does it, visibly.
_client = OpenAI(
    base_url=config.LLM_BASE_URL,
    api_key=config.GROQ_API_KEY,
    timeout=config.LLM_TIMEOUT_S,
    max_retries=0,
)

_TRANSIENT = (APIConnectionError, APITimeoutError, RateLimitError, InternalServerError)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    retry=retry_if_exception_type(_TRANSIENT),
    reraise=True,
)
def _call(messages: list[dict], json_mode: bool = True) -> tuple[str, int, int]:
    # In JSON mode the provider validates the output itself and can reject it with a 400.
    extra = {"response_format": {"type": "json_object"}} if json_mode else {}
    response = _client.chat.completions.create(
        model=config.LLM_MODEL,
        messages=messages,
        temperature=0,  # as deterministic as possible
        max_tokens=config.LLM_MAX_TOKENS,
        **extra,
    )
    content = response.choices[0].message.content or ""
    usage = response.usage
    return content, (usage.prompt_tokens if usage else 0), (usage.completion_tokens if usage else 0)


def _clean(raw: str) -> str:
    """Strip ```json fences and any text around the outermost { ... }."""
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
    start, end = raw.find("{"), raw.rfind("}")
    return raw[start:end + 1] if start != -1 and end > start else raw


def chat_json(system: str, user: str, schema: type[BaseModel], tracer: Tracer | None = None,
              label: str = "llm", max_repairs: int = 1) -> BaseModel:
    """Ask the LLM for JSON matching `schema`. Validates; on bad JSON, asks once to repair."""
    schema_json = json.dumps(schema.model_json_schema())
    messages = [
        {"role": "system", "content": f"{system}\n\nReturn ONLY a JSON object matching this JSON Schema. "
                                      f"No prose, no markdown.\nSchema: {schema_json}"},
        {"role": "user", "content": user},
    ]
    json_mode = True
    last_error = ""
    for attempt in range(max_repairs + 1):
        start = time.time()
        try:
            try:
                raw, tokens_in, tokens_out = _call(messages, json_mode)
            except BadRequestError as e:
                # The provider's strict JSON mode rejected the output. Retry in plain mode and
                # let OUR Pydantic validation (and repair step) decide whether it is usable.
                if not json_mode or "json" not in str(e).lower():
                    raise
                json_mode = False
                if tracer:
                    tracer.log("llm_json_mode_rejected", label=label, error=str(e)[:300])
                raw, tokens_in, tokens_out = _call(messages, json_mode)
        except Exception as e:
            if tracer:
                tracer.log("llm_error", label=label, error=str(e)[:300])
            raise LLMError(f"{label}: provider call failed: {e}") from e

        latency = round(time.time() - start, 2)
        try:
            result = schema.model_validate_json(_clean(raw))
        except ValidationError as e:
            last_error = str(e)[:500]
            if tracer:
                tracer.log("llm_invalid_output", label=label, attempt=attempt, latency_s=latency, error=last_error)
            # Show the model its mistake and ask for a corrected reply.
            messages += [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"Your reply was invalid: {last_error}\nReturn ONLY the corrected JSON object."},
            ]
            continue

        if tracer:
            tracer.log("llm_call", label=label, attempt=attempt, latency_s=latency,
                       tokens_in=tokens_in, tokens_out=tokens_out, json_mode=json_mode)
        return result

    raise LLMError(f"{label}: no valid JSON after {max_repairs + 1} attempts: {last_error}")