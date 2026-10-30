from pydantic import ValidationError
from app.schemas import Plan, SubTask
from app.tracing import Tracer

tracer = Tracer("What are the top open-source vector databases?")

plan = Plan(
    question="What are the top open-source vector databases?",
    sub_tasks=[SubTask(question="Which are most used?", search_queries=["top open source vector databases"])],
    success_criteria=["Names 3 databases", "Compares licensing"],
)
tracer.log("plan_created", plan=plan.model_dump())  # model_dump() -> plain dict
print("valid plan OK, trace file:", tracer.path)

# Malformed data must be rejected, not silently accepted
try:
    Plan(question="q", sub_tasks="oops", success_criteria=[])
except ValidationError as e:
    tracer.log("validation_error", errors=str(e))
    print("bad plan correctly rejected")