from app.agent import run_research
from app.schemas import Finding, Source, SynthesisDraft
from app.verifier import compute_confidence, verify_findings

# ---------- Offline checks (instant, no network) ----------
src = Source(id="S1", url="https://a.com/x", title="t", domain="a.com",
             text="Qdrant is an open\u2011source vector database written in Rust and supports   hybrid search.")
draft = SynthesisDraft(
    short_answer="x", limitations=[], next_steps=[],
    key_findings=[
        Finding(claim="good", source_id="S1", quote="an open-source vector database written in Rust"),   # different dash + spacing
        Finding(claim="fabricated", source_id="S1", quote="Qdrant is a closed-source database that costs a lot of money"),
        Finding(claim="too short", source_id="S1", quote="vector database"),
        Finding(claim="bad id", source_id="S9", quote="an open-source vector database written in Rust"),
    ],
)
verified, rejected = verify_findings(draft, [src])
assert len(verified) == 1 and verified[0].verified and len(rejected) == 3
print("1. verifier accepts the real quote and rejects fabricated, short and bad-id ones OK")
for r in rejected:
    print("   rejected:", r["claim"], "->", r["reason"])


def fake_sources(n, flags=None):
    return [Source(id=f"S{i}", url=f"https://site{i}.com/p", title="t", domain=f"site{i}.com", flags=flags or []) for i in range(1, n + 1)]


def fake_findings(ids):
    return [Finding(claim="c", source_id=i, quote="q", verified=True) for i in ids]


level, _ = compute_confidence(fake_findings(["S1", "S1", "S1", "S1"]), 4, fake_sources(1))
assert level == "low"          # all evidence from one site
level, _ = compute_confidence(fake_findings(["S1", "S2", "S2"]), 4, fake_sources(2))
assert level == "medium"
level, _ = compute_confidence(fake_findings(["S1", "S2", "S3", "S3"]), 4, fake_sources(3))
assert level == "high"
level, _ = compute_confidence(fake_findings(["S1", "S2", "S3", "S3"]), 4, fake_sources(3, ["kind:vendor_marketing"]))
assert level == "medium"       # three sites, but none independent of vendor marketing
print("2. confidence rules OK (one site=low, two=medium, three independent=high, vendor-only=medium)")

# ---------- Full pipeline ----------
q = "Compare the top 3 open-source vector databases for a startup building RAG products"
answer, tracer = run_research(q)
print("\n3. FULL RUN")
print(answer.model_dump_json(indent=2))
assert all(f.verified for f in answer.key_findings)
assert answer.confidence in ("high", "medium", "low")
print("\ntrace:", tracer.path)