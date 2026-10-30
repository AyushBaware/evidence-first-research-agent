import ipaddress
import re
import time
from urllib.parse import urlparse

import httpx
import trafilatura
from tenacity import retry, retry_if_exception, stop_after_attempt, wait_exponential

from app import config
from app.schemas import ToolResult
from app.tools.common import is_transient

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; ResearchAgentBot/0.1)"}

# Patterns that often show up in prompt-injection attempts inside web pages.
INJECTION_PATTERNS = {
    "instruction_override": r"ignore (all |any |the )?(previous|prior|above|earlier) (instructions|prompts?)",
    "disregard": r"disregard (all |any |the )?(previous|prior|above|system)",
    "role_hijack": r"you are now\b",
    "prompt_leak": r"(reveal|print|show|repeat) (your|the) (system )?(prompt|instructions)",
    "new_instructions": r"new instructions\s*:",
}


def find_injection_flags(text: str) -> list[str]:
    return [name for name, pattern in INJECTION_PATTERNS.items() if re.search(pattern, text, re.IGNORECASE)]


def _unsafe_reason(url: str) -> str | None:
    """Basic SSRF guard: only public http(s) URLs. Returns a reason, or None if OK."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return "only http/https URLs are allowed"
    host = parsed.hostname
    if not host:
        return "missing host"
    if host == "localhost":
        return "localhost is blocked"
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return None  # a normal domain name, not an IP address
    if ip.is_private or ip.is_loopback or ip.is_link_local:
        return "private IP addresses are blocked"
    return None


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=1, max=4),
    retry=retry_if_exception(is_transient),
    reraise=True,
)
def _download(url: str) -> str:
    # Timeout is per network operation (connect/read), not a total cap.
    with httpx.stream("GET", url, headers=HEADERS, timeout=config.TOOL_TIMEOUT_S, follow_redirects=True) as response:
        response.raise_for_status()
        content_type = response.headers.get("content-type", "")
        if "html" not in content_type and "text/plain" not in content_type:
            raise ValueError(f"unsupported content-type: {content_type or 'unknown'}")
        chunks, size = [], 0
        for chunk in response.iter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > config.MAX_DOWNLOAD_BYTES:
                break  # stop downloading huge pages
        encoding = response.encoding or "utf-8"
    return b"".join(chunks).decode(encoding, errors="replace")


def fetch_page(url: str) -> ToolResult:
    """Never raises. Always returns a ToolResult."""
    start = time.time()

    def fail(message: str) -> ToolResult:
        return ToolResult(tool="fetch_page", ok=False, error=message[:300], data={"url": url}, latency_s=round(time.time() - start, 2))

    reason = _unsafe_reason(url)
    if reason:
        return fail(f"blocked url: {reason}")
    try:
        html = _download(url)
    except Exception as e:
        return fail(f"{type(e).__name__}: {e}")

    text = trafilatura.extract(html, include_comments=False, include_tables=True)
    if not text or len(text.strip()) < 200:
        return fail("no extractable text (page may be JavaScript-rendered or paywalled)")

    truncated = len(text) > config.MAX_PAGE_CHARS
    text = text[: config.MAX_PAGE_CHARS]
    return ToolResult(
        tool="fetch_page",
        ok=True,
        data={"url": url, "text": text, "truncated": truncated, "flags": find_injection_flags(text)},
        latency_s=round(time.time() - start, 2),
    )