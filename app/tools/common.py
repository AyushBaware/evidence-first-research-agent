from urllib.parse import urlparse

import httpx

import re


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


def site_of(url: str) -> str:
    """Registrable site: ca.finance.yahoo.com -> yahoo.com, bbc.co.uk -> bbc.co.uk."""
    host = domain_of(url)
    parts = host.split(".")
    if len(parts) >= 3 and len(parts[-1]) == 2 and parts[-2] in {"co", "com", "org", "net", "gov", "ac", "edu"}:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def escape_untrusted(text: str) -> str:
    """Stop fetched text from closing our <source> wrapper tags in a prompt."""
    return re.sub(r"<\s*(/?)\s*source", r"[\1source", text, flags=re.IGNORECASE)