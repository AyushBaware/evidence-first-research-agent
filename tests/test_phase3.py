from app.executor import gather
from app.planner import make_plan
from app.tracing import Tracer

QUESTIONS = [
    "Compare the top 3 open-source vector databases for a startup building RAG products",
    "How do AI agents help with loan collections in India?",
]

for q in QUESTIONS:
    print("\n" + "=" * 80)
    print("QUESTION:", q)
    tracer = Tracer(q)
    plan = make_plan(q, tracer)
    for i, task in enumerate(plan.sub_tasks, 1):
        print(f"  sub-task {i}: {task.question}  {task.search_queries}")
    print("  criteria:", plan.success_criteria)
    print("  assumptions:", plan.assumptions)

    result = gather(plan, tracer)
    print(f"\n  searches={result.searches_used} fetch_attempts={result.fetch_attempts} sources={len(result.sources)}")
    for s in result.sources:
        print(f"   {s.id} {s.domain:35} {len(s.text):5} chars flags={s.flags}")
    print("  notes:", result.notes)
    print("  trace:", tracer.path)
    assert len(result.sources) >= 1, "expected at least one source"