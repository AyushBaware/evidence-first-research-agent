import time

import httpx
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app import config
from app.schemas import ToolResult
from app.tools.common import is_transient

TAVILY_URL = "https://api.tavily.com/search"


@retry(
    stop=stop_after_attempt(3),                                # at most 3 tries
    wait=wait_exponential(multiplier=1, min=1, max=6),         # wait 1s, 2s, ... between tries
    retry=retry_if_exception(is_transient),                    # only retry transient errors
    reraise=True,                                              # after the last try, raise the real error
)
def _request(query: str, max_results: int) -> dict:
    response = httpx.post(
        TAVILY_URL,
        json={"query": query, "max_results": max_results, "search_depth": "basic"},
        headers={"Authorization": f"Bearer {config.TAVILY_API_KEY}"},
        timeout=config.TOOL_TIMEOUT_S,
    )
    response.raise_for_status()  # turns 4xx/5xx into an exception
    return response.json()


def web_search(query: str, max_results: int = 5) -> ToolResult:
    """Never raises. Always returns a ToolResult."""
    start = time.time()

    def elapsed() -> float:
        return round(time.time() - start, 2)

    try:
        payload = _request(query, max_results)
    except Exception as e:
        return ToolResult(tool="web_search", ok=False, error=f"{type(e).__name__}: {e}"[:300], latency_s=elapsed())

    raw_items = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(raw_items, list):
        return ToolResult(tool="web_search", ok=False, error="malformed response: no results list", latency_s=elapsed())

    results, skipped = [], 0
    for item in raw_items:
        url = item.get("url") if isinstance(item, dict) else None
        title = item.get("title") if isinstance(item, dict) else None
        if not (isinstance(url, str) and url.startswith(("http://", "https://")) and isinstance(title, str) and title.strip()):
            skipped += 1  # malformed item: skip it, don't trust it
            continue
        results.append({
            "title": title.strip(),
            "url": url,
            "snippet": str(item.get("content", ""))[:500],
            "score": item.get("score", 0),
        })

    if not results:
        return ToolResult(tool="web_search", ok=False, error=f"no valid results (skipped {skipped})", latency_s=elapsed())
    return ToolResult(tool="web_search", ok=True, data={"query": query, "results": results, "skipped": skipped}, latency_s=elapsed())