import argparse
import sys
from pathlib import Path

from app.agent import run_research
from app.schemas import FinalAnswer


def render(a: FinalAnswer) -> str:
    lines = [f"QUESTION: {a.question}", "", f"SHORT ANSWER ({a.confidence.upper()} confidence):", a.short_answer, "", "KEY FINDINGS:"]
    for i, f in enumerate(a.key_findings, 1):
        lines.append(f"  {i}. {f.claim} [{f.source_id}] ({f.support})")
        lines.append(f'     "{f.quote[:160]}"')
    if not a.key_findings:
        lines.append("  (none)")
    lines += ["", "SOURCES:"] + [f"  [{s.id}] {s.title} - {s.url}" for s in a.sources]
    lines += ["", "CONFIDENCE REASONS:"] + [f"  - {r}" for r in a.confidence_reasons]
    lines += ["", "LIMITATIONS / ASSUMPTIONS:"] + [f"  - {x}" for x in a.limitations]
    lines += ["", "NEXT STEPS:"] + [f"  - {x}" for x in a.next_steps]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Evidence-first research agent")
    parser.add_argument("question")
    parser.add_argument("--json", action="store_true", help="print raw JSON instead of the readable report")
    parser.add_argument("--save", help="also save the JSON answer to this path, e.g. samples/vector_db.json")
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles choke on characters like non-breaking hyphens
    answer, tracer = run_research(args.question)

    if args.save:
        path = Path(args.save)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(answer.model_dump_json(indent=2), encoding="utf-8")

    print(answer.model_dump_json(indent=2) if args.json else render(answer))
    print(f"\ntrace: {tracer.path}")


if __name__ == "__main__":
    main()