from app.judge import judge_findings
from app.schemas import Finding
from app.tracing import Tracer

QUOTE = "| Qdrant | Self-hosted, performance-critical RAG | Self-hosted + cloud | ~2.1 ms p50 / ~1,200 QPS (1M vectors) | Smaller ecosystem than major platforms |"

findings = [
    Finding(claim="Qdrant shows about 2.1 ms p50 latency at 1M vectors", source_id="S1", quote=QUOTE, verified=True),
    Finding(claim="Qdrant has the lowest latency of any vector database", source_id="S1", quote=QUOTE, verified=True),
    Finding(claim="Qdrant is written in Python and costs $500 per month", source_id="S1", quote=QUOTE, verified=True),
]
kept, dropped = judge_findings(findings, Tracer("judge test"))
for f in kept:
    print("KEPT   ", f.support.ljust(9), f.claim)
for d in dropped:
    print("DROPPED", d["claim"], "->", d["reason"])

assert any(f.claim.startswith("Qdrant shows") and f.support == "supported" for f in kept), "faithful claim should be supported"
assert not any(f.claim.endswith("$500 per month") for f in kept), "false claim should be dropped"
assert not any(f.claim.startswith("Qdrant has the lowest") and f.support == "supported" for f in kept), "overreach must not count as supported"
print("judge OK")