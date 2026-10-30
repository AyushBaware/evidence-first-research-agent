from collections import defaultdict

from pydantic import BaseModel, Field

from app import config
from app.schemas import Plan, Source
from app.tools.common import domain_of, site_of
from app.tools.fetch import fetch_page, find_injection_flags
from app.tools.search import web_search
from app.tracing import Tracer


class GatherResult(BaseModel):
    sources: list[Source]
    searches_used: int
    fetch_attempts: int
    notes: list[str] = Field(default_factory=list)  # honest problems, later shown as limitations


def _norm(url: str) -> str:
    """Normalize a URL so the same page isn't fetched twice."""
    return url.split("#")[0].rstrip("/").lower()


def _score(item: dict) -> float:
    try:
        return float(item.get("score") or 0)
    except (TypeError, ValueError):
        return 0.0


def _run_search(query: str, budget: dict, tracer: Tracer, pool: dict) -> None:
    if budget["searches"] >= config.MAX_SEARCHES:
        tracer.log("budget_exhausted", kind="search", query=query)
        return
    budget["searches"] += 1
    result = web_search(query)
    tracer.log(
        "tool_call", tool="web_search", query=query, ok=result.ok,
        latency_s=result.latency_s, error=result.error,
        n_results=len(result.data["results"]) if result.ok else 0,
    )
    if not result.ok:
        return
    for item in result.data["results"]:
        key = _norm(item["url"])
        if key not in pool or _score(item) > _score(pool[key]):
            pool[key] = item


def gather(plan: Plan, tracer: Tracer) -> GatherResult:
    budget = {"searches": 0, "fetches": 0}
    sources: list[Source] = []
    seen_urls: set[str] = set()
    domain_count: dict[str, int] = defaultdict(int)  # a dict whose missing keys start at 0
    notes: list[str] = []

    for i, task in enumerate(plan.sub_tasks):
        # ---- 1. SEARCH ----
        pool: dict[str, dict] = {}
        for query in task.search_queries[: config.MAX_QUERIES_PER_TASK]:
            _run_search(query, budget, tracer, pool)

        if len(pool) < 2:  # thin or failed: retry with the sub-task question as the query
            tracer.log("search_thin", task=i, found=len(pool), action="fallback_query", query=task.question)
            _run_search(task.question, budget, tracer, pool)

        ranked = sorted(pool.values(), key=_score, reverse=True)
        if not ranked:
            notes.append(f"Sub-task {i + 1} ('{task.question[:80]}') found no search results.")
            continue

        # ---- 2. DECIDE which pages to read, then FETCH ----
        got = 0
        snippet_fallback = None
        for rank, item in enumerate(ranked, start=1):
            if got >= config.PAGES_PER_TASK:
                break
            if budget["fetches"] >= config.MAX_FETCH_ATTEMPTS:
                tracer.log("budget_exhausted", kind="fetch")
                break
            key, domain = _norm(item["url"]), site_of(item["url"])
            if key in seen_urls:
                continue
            if domain_count[domain] >= config.MAX_PER_DOMAIN:
                tracer.log("tool_skip", task=i, url=item["url"], reason=f"domain limit reached ({domain})")
                continue

            tracer.log("tool_decision", task=i, tool="fetch_page", url=item["url"],
                       reason=f"search rank {rank}, score {_score(item):.2f}, new domain count {domain_count[domain]}")
            budget["fetches"] += 1
            seen_urls.add(key)
            page = fetch_page(item["url"])
            tracer.log("tool_call", tool="fetch_page", url=item["url"], ok=page.ok,
                       latency_s=page.latency_s, error=page.error,
                       flags=page.data.get("flags") if page.ok else None)

            if page.ok:
                sources.append(Source(
                    id=f"S{len(sources) + 1}", url=item["url"], title=item["title"], domain=domain,
                    snippet=item["snippet"], text=page.data["text"], flags=page.data["flags"],
                ))
                domain_count[domain] += 1
                got += 1
            elif snippet_fallback is None and len(item["snippet"]) >= 80:
                snippet_fallback = item  # remember the best page we couldn't read

        # ---- 3. DEGRADE GRACEFULLY ----
        if got == 0 and snippet_fallback is not None:
            item = snippet_fallback
            sources.append(Source(
                id=f"S{len(sources) + 1}", url=item["url"], title=item["title"], domain=domain_of(item["url"]),
                snippet=item["snippet"], text=item["snippet"],
                flags=["snippet_only"] + find_injection_flags(item["snippet"]),
            ))
            notes.append(f"Sub-task {i + 1}: no page could be read; used a search snippet only.")
            tracer.log("degraded", task=i, mode="snippet_only", url=item["url"])
        elif got == 0:
            notes.append(f"Sub-task {i + 1}: no readable pages found.")

    tracer.log("gather_done", sources=len(sources), searches=budget["searches"], fetches=budget["fetches"])
    return GatherResult(sources=sources, searches_used=budget["searches"],
                        fetch_attempts=budget["fetches"], notes=notes)