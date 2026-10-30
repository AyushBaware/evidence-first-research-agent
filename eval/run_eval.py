import json
import sys
import time
from pathlib import Path

import yaml
from pydantic import BaseModel

from app import config
from app.agent import run_research
from app.llm import LLMError, chat_json
from app.tools.fetch import fetch_page
from app.tracing import Tracer
from app.verifier import normalize

RESULTS = Path("eval/results")

BASELINE_SYSTEM = """Answer the research question from your own knowledge. You have NO browsing tools.
Give a 2-4 sentence short_answer, then up to 6 findings. Each finding has a claim, a source url,
and a quote: your best attempt at a verbatim sentence from that page."""


class BLFinding(BaseModel):
    claim: str
    url: str
    quote: str


class BaselineAnswer(BaseModel):
    short_answer: str
    findings: list[BLFinding]


def trace_stats(path) -> dict:
    events = [json.loads(line) for line in Path(path).read_text(encoding="utf-8").splitlines()]
    tokens = sum(e.get("tokens_in", 0) + e.get("tokens_out", 0) for e in events if e["event"] == "llm_call")
    drafted = next((e["kept"] for e in events if e["event"] == "synthesis_done"), 0)
    verified = next((e["verified"] for e in events if e["event"] == "verification"), 0)
    return {"tokens": tokens, "drafted": drafted, "quote_check_passed": verified}


def run_agent(q: str) -> dict:
    start = time.time()
    answer, tracer = run_research(q)
    stats = trace_stats(tracer.path)
    claimed = stats["drafted"]
    return {
        "latency_s": round(time.time() - start, 1), "tokens": stats["tokens"],
        "confidence": answer.confidence, "sources": len(answer.sources),
        "claimed_quotes": claimed, "valid_quotes": stats["quote_check_passed"],
        "final_findings": len(answer.key_findings),
        "short_answer": answer.short_answer, "trace": str(tracer.path),
    }, answer


def run_baseline(q: str) -> dict:
    """One LLM call, no tools. Each cited URL is fetched and the quote is checked against the real page."""
    start = time.time()
    tracer = Tracer(q)
    try:
        ans = chat_json(BASELINE_SYSTEM, f"Research question: {q}", BaselineAnswer, tracer=tracer, label="baseline")
    except LLMError as e:
        return {"latency_s": round(time.time() - start, 1), "error": str(e)[:200]}
    pages: dict[str, str | None] = {}
    valid = 0
    for f in ans.findings[:6]:
        if f.url not in pages:
            r = fetch_page(f.url)
            pages[f.url] = r.data["text"] if r.ok else None
        text = pages[f.url]
        quote = normalize(f.quote)
        if text and len(quote.split()) >= config.MIN_QUOTE_WORDS and quote in normalize(text):
            valid += 1
    return {
        "latency_s": round(time.time() - start, 1), "tokens": trace_stats(tracer.path)["tokens"],
        "sources": len({f.url for f in ans.findings[:6]}), "claimed_quotes": len(ans.findings[:6]),
        "valid_quotes": valid, "unreachable_urls": sum(1 for t in pages.values() if t is None),
        "short_answer": ans.short_answer, "trace": str(tracer.path),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    RESULTS.mkdir(parents=True, exist_ok=True)
    queries = yaml.safe_load(Path("eval/queries.yaml").read_text(encoding="utf-8"))
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv
    for item in queries:
        if wanted and item["id"] not in wanted:
            continue
        out = RESULTS / f"{item['id']}.json"
        if out.exists() and not force:
            print("skip (already done):", item["id"])
            continue
        print("\n===", item["id"], "|", item["question"])
        agent, answer = run_agent(item["question"])
        (RESULTS / f"{item['id']}.answer.json").write_text(answer.model_dump_json(indent=2), encoding="utf-8")
        print("  agent   :", {k: v for k, v in agent.items() if k not in ("short_answer", "trace")})
        baseline = run_baseline(item["question"])
        print("  baseline:", {k: v for k, v in baseline.items() if k not in ("short_answer", "trace")})
        out.write_text(json.dumps({**item, "agent": agent, "baseline": baseline}, indent=2), encoding="utf-8")

    rows = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(RESULTS.glob("q*.json")) if not p.name.endswith(".answer.json")]
    lines = ["| Query | Mode | Confidence | Sources | Valid quotes / claimed | Tokens | Latency (s) |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        a, b = r["agent"], r["baseline"]
        lines.append(f"| {r['id']} | agent | {a['confidence']} | {a['sources']} | {a['valid_quotes']}/{a['claimed_quotes']} | {a['tokens']} | {a['latency_s']} |")
        if "error" in b:
            lines.append(f"| {r['id']} | baseline | - | - | failed: {b['error'][:60]} | - | {b['latency_s']} |")
        else:
            lines.append(f"| {r['id']} | baseline | n/a | {b['sources']} | {b['valid_quotes']}/{b['claimed_quotes']} | {b['tokens']} | {b['latency_s']} |")
    Path("eval/results_table.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n" + "\n".join(lines))


if __name__ == "__main__":
    main()