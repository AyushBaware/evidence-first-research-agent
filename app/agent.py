import time

from app.executor import gather
from app.filtering import filter_sources
from app.judge import judge_findings, write_short_answer
from app.llm import LLMError
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

        # Check 1 (code): does each quote exist in its source?
        verified, rejected = verify_findings(draft, filtered.kept)
        tracer.log("verification", verified=len(verified), rejected=rejected)

        limitations = list(draft.limitations) + notes + [f"Assumption: {a}" for a in plan.assumptions]

        # Check 2 (LLM judge, sees only claim + quote): does the quote support the claim?
        judged = True
        try:
            checked, unsupported = judge_findings(verified, tracer)
        except LLMError as e:
            checked, unsupported, judged = verified, [], False
            tracer.log("judge_failed", error=str(e)[:300])
            limitations.append("The claim-support check was unavailable, so confidence is capped at medium.")

        level, reasons = compute_confidence(checked, len(draft.key_findings), filtered.kept, judged=judged)

        removed = len(rejected) + len(unsupported)
        if removed:
            limitations.append(
                f"{removed} of {len(draft.key_findings)} drafted findings were removed: {len(rejected)} had quotes that "
                f"could not be verified in the source, and {len(unsupported)} had quotes that did not support the claim."
            )
        partial = sum(1 for f in checked if f.support == "partial")
        if partial:
            limitations.append(f"{partial} finding(s) are only partially supported by their quote and do not count toward confidence.")
        limitations.append(
            "Quote verification is an exact-match check and the support check is an LLM judgment; "
            "neither guarantees that a claim is true."
        )

        # Short answer is regenerated from checked findings only.
        supported = [f for f in checked if f.support == "supported"] if judged else list(checked)
        if len(supported) < 2:
            short = INSUFFICIENT + " Any partially supported findings are listed below."
        else:
            try:
                short = write_short_answer(question, supported, tracer)
            except LLMError as e:
                tracer.log("short_answer_failed", error=str(e)[:300])
                short = draft.short_answer
                limitations.append("The short answer could not be regenerated from checked findings and may include unverified statements.")
            if level == "low":
                short = "Low confidence: " + short

        cited = {f.source_id for f in checked}
        sources_out = [s.model_copy(update={"text": ""}) for s in filtered.kept if s.id in cited]  # drop bulky page text

        answer = FinalAnswer(
            question=question, short_answer=short, key_findings=checked, sources=sources_out,
            confidence=level, confidence_reasons=reasons, limitations=limitations, next_steps=draft.next_steps,
        )
        tracer.log("run_done", confidence=level, findings=len(checked), seconds=round(time.time() - started, 1))
        return answer, tracer
    except Exception as e:  # last line of defence: the caller always gets a valid answer object
        return _failed(question, f"Unexpected failure: {type(e).__name__}: {e}", tracer), tracer