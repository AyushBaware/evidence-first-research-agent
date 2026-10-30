import re
import unicodedata

from app import config
from app.schemas import Finding, Source, SynthesisDraft
from app.tools.common import site_of

# Map fancy dashes and quotes to plain ones so formatting differences don't cause false rejections.
_DASHES = dict.fromkeys(map(ord, "\u2010\u2011\u2012\u2013\u2014\u2015\u2212"), "-")
_QUOTES = {ord("\u2018"): "'", ord("\u2019"): "'", ord("\u201c"): '"', ord("\u201d"): '"'}

WEAK_KINDS = {"kind:vendor_marketing", "kind:press_release"}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.translate(_DASHES).translate(_QUOTES)
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_findings(draft: SynthesisDraft, sources: list[Source]) -> tuple[list[Finding], list[dict]]:
    """Return (verified findings, rejected findings with reasons). Our code decides, not the LLM."""
    by_id = {s.id: s for s in sources}
    verified: list[Finding] = []
    rejected: list[dict] = []
    for f in draft.key_findings:
        src = by_id.get(f.source_id)
        quote = normalize(f.quote)
        if src is None:
            reason = "unknown source id"
        elif len(quote.split()) < config.MIN_QUOTE_WORDS:
            reason = "quote too short"
        elif quote not in normalize(src.text[: config.SYNTH_CHARS_PER_SOURCE]):
            reason = "quote not found in source text"
        else:
            reason = None

        if reason:
            rejected.append({"claim": f.claim[:120], "source_id": f.source_id, "reason": reason})
        else:
            verified.append(f.model_copy(update={"verified": True}))
    return verified, rejected


def compute_confidence(findings: list[Finding], total: int, sources: list[Source], judged: bool = True) -> tuple[str, list[str]]:
    """Confidence from evidence signals, never from the LLM's own opinion."""
    by_id = {s.id: s for s in sources}
    counted = [f for f in findings if f.support == "supported"] if judged else list(findings)
    evidence = {(f.source_id, normalize(f.quote)) for f in counted}   # distinct (source, quote) pairs
    cited = {f.source_id for f in counted}
    sites = {site_of(by_id[i].url) for i in cited}
    independent = {site_of(by_id[i].url) for i in cited if not (set(by_id[i].flags) & WEAK_KINDS)}
    ratio = len(counted) / total if total else 0.0
    n = len(evidence)

    how = ("verified in the source text and judged supported by their quote" if judged
           else "verified in the source text (claim-support check unavailable)")
    reasons = [
        f"{len(counted)} of {total} drafted findings were {how} ({ratio:.0%}).",
        f"They rest on {n} distinct quote(s) from {len(sites)} distinct site(s): {', '.join(sorted(sites)) or 'none'}.",
        f"{len(independent)} of those site(s) are not vendor marketing or press releases.",
    ]

    needs = None
    if ratio >= 0.8 and n >= 4 and len(sites) >= 3 and len(independent) >= 2:
        level = "high"
    elif ratio >= 0.5 and n >= 3 and len(sites) >= 2:
        level, needs = "medium", "high needs 80%+ supported, 4+ distinct quotes, 3+ sites, 2+ independent sites"
    else:
        level, needs = "low", "medium needs 50%+ supported, 3+ distinct quotes, 2+ sites"
    if needs:
        reasons.append(f"Not higher because {needs}.")
        if level == "high" and any("snippet_only" in by_id[i].flags for i in cited):
            level = "medium"
            reasons.append("Capped at medium because some evidence comes from search snippets, not full pages.")
    if not judged and level == "high":
        level = "medium"
        reasons.append("Capped at medium because the claim-support check was unavailable.")
    return level, reasons