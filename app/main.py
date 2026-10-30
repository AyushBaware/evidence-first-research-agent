from fastapi import FastAPI
from pydantic import BaseModel, Field

from app.agent import run_research
from app.schemas import FinalAnswer

app = FastAPI(title="Evidence-First Research Agent")


class ResearchRequest(BaseModel):
    question: str = Field(min_length=10, max_length=500)  # FastAPI rejects bad input with a 422


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/research", response_model=FinalAnswer)
def research(req: ResearchRequest) -> FinalAnswer:
    answer, _tracer = run_research(req.question)  # never raises; failures come back as low-confidence answers
    return answer