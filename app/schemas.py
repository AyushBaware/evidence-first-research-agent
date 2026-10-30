from typing import Any, Literal
from pydantic import BaseModel, Field


# ---------- Planning ----------
class SubTask(BaseModel):
    question: str                      # one focused sub-question
    search_queries: list[str]          # queries the executor will run for it


class Plan(BaseModel):
    question: str
    sub_tasks: list[SubTask] = Field(min_length=1, max_length=4)  # bound the work
    success_criteria: list[str]        # what a good answer must contain
    assumptions: list[str] = Field(default_factory=list)


# ---------- Tools ----------
class ToolResult(BaseModel):
    tool: str
    ok: bool
    data: Any = None                   # whatever the tool returned
    error: str | None = None
    latency_s: float = 0.0


class Source(BaseModel):
    id: str                            # "S1", "S2", ... used for citations
    url: str
    title: str
    domain: str
    snippet: str = ""
    text: str = ""                     # fetched page text (truncated)
    relevance: float = 0.0             # 0..1 score from filtering
    flags: list[str] = Field(default_factory=list)  # e.g. "injection_suspected"


# ---------- Answer ----------
class Finding(BaseModel):
    claim: str
    source_id: str                     # must match a Source.id
    quote: str                         # verbatim text from that source
    verified: bool = False             # set by OUR code, not by the LLM


class SynthesisDraft(BaseModel):
    """What the LLM is asked to return. Confidence is NOT here on purpose."""
    short_answer: str
    key_findings: list[Finding]
    limitations: list[str]
    next_steps: list[str]


class FinalAnswer(BaseModel):
    """What we return to the user after verification."""
    question: str
    short_answer: str
    key_findings: list[Finding]
    sources: list[Source]
    confidence: Literal["high", "medium", "low"]
    confidence_reasons: list[str]
    limitations: list[str]
    next_steps: list[str]