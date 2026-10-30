from urllib.parse import urlparse

import httpx


def domain_of(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def is_transient(exc: Exception) -> bool:
    """True for errors worth retrying: timeouts, network blips, 429, 5xx."""
    if isinstance(exc, httpx.TransportError):  # includes timeouts and connection errors
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return code == 429 or code >= 500
    return False  # 404, 403, bad content, etc.: retrying won't help