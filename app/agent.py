import time

from app.executor import gather
from app.filtering import filter_sources
from app.planner import make_plan
from app.schemas import FinalAnswer
from app.synthesizer import synthesize
from app.tracing import Tracer
from app.verifier import compute_confidence, verify_findings

INSUFFICIENT = "Insufficient verified evidence to answer this question reliably."


def _failed(question: str, reason: str, tracer: Tracer, notes: list[str] | None = None) -> FinalAnswer:
    tracer.log("run_failed", reason=reason)
    return FinalAnswer(
        question=question, short_answer=INSUFFICIENT, key_findings=[], sources=[],
        confidence="low", confidence_reasons=[reason], limitations=[reason] + (notes or []),
        next_steps=["Retry the question, possibly rephrased.", f"Inspect the trace to see which stage failed: {tracer.path}"],
    )


def run_research(question: str) -> tuple[FinalAnswer, Tracer]:
    """Always returns a valid FinalAnswer. Any failure becomes a low-confidence answer."""
    tracer = Tracer(question)
    started = time.time()
    try:
        plan = make_plan(question, tracer)

        gathered = gather(plan, tracer)
        notes = list(gathered.notes)
        if not gathered.sources:
            return _failed(question, "No sources could be retrieved.", tracer, notes), tracer

        filtered = filter_sources(question, gathered.sources, tracer, criteria=plan.success_criteria)
        notes += filtered.notes
        if filtered.dropped:
            notes.append(f"{len(filtered.dropped)} candidate source(s) were dropped (quarantine, low relevance or cost cap); see the trace.")
        if not filtered.kept:
            return _failed(question, "No usable sources remained after filtering.", tracer, notes), tracer

        draft = synthesize(question, plan, filtered.kept, tracer)

        verified, rejected = verify_findings(draft, filtered.kept)
        tracer.log("verification", verified=len(verified), rejected=rejected)
        level, reasons = compute_confidence(verified, len(draft.key_findings), filtered.kept)

        limitations = list(draft.limitations) + notes + [f"Assumption: {a}" for a in plan.assumptions]
        if rejected:
            limitations.append(
                f"{len(rejected)} of {len(draft.key_findings)} drafted findings were removed because their quotes "
                "could not be verified. The short answer was written before verification and may still mention them."
            )
        limitations.append("Verification confirms each quote exists in its source; it does not prove the claim follows from the quote.")

        short = draft.short_answer
        if len(verified) < 2:
            short = INSUFFICIENT + " Any partial findings are listed below."
        elif level == "low":
            short = "Low confidence: " + short

        cited = {f.source_id for f in verified}
        sources_out = [s.model_copy(update={"text": ""}) for s in filtered.kept if s.id in cited]  # drop bulky page text

        answer = FinalAnswer(
            question=question, short_answer=short, key_findings=verified, sources=sources_out,
            confidence=level, confidence_reasons=reasons, limitations=limitations, next_steps=draft.next_steps,
        )
        tracer.log("run_done", confidence=level, verified=len(verified), seconds=round(time.time() - started, 1))
        return answer, tracer
    except Exception as e:  # last line of defence: the caller always gets a valid answer object
        return _failed(question, f"Unexpected failure: {type(e).__name__}: {e}", tracer), tracer