"""Analyse: written answers from a local model, grounded in computed facts."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field, model_validator

from munim.analyse import Goal, analyse
from munim.ask.llm import LLMError

router = APIRouter(prefix="/api")


class AnalyseIn(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    goal_amount: float | None = Field(default=None, gt=0, le=1e10)
    goal_months: int | None = Field(default=None, ge=1, le=600)
    goal_label: str | None = Field(default=None, max_length=80)

    @model_validator(mode="after")
    def _both_or_neither(self):
        if (self.goal_amount is None) != (self.goal_months is None):
            raise ValueError("A goal needs both an amount and a number of months.")
        return self


class AnalyseStatus(BaseModel):
    ready: bool
    model: str | None
    reachable: bool
    has_model: bool
    problem: str | None


@router.get("/analyse/status", response_model=AnalyseStatus)
def analyse_status(request: Request):
    chat = request.app.state.analyst
    if chat is None:
        return AnalyseStatus(ready=False, model=None, reachable=False, has_model=False, problem=request.app.state.analyst_problem)
    s = chat.status()
    problem = None
    if not s["reachable"]:
        problem = "Ollama is not running. Start it with `ollama serve` (or open the Ollama app)."
    elif not s["has_model"]:
        problem = f"The model is not downloaded yet. Run `ollama pull {chat.name}`."
    return AnalyseStatus(ready=problem is None, model=chat.name, problem=problem, **s)


@router.post("/analyse")
def run_analyse(body: AnalyseIn, request: Request):
    chat = request.app.state.analyst
    if chat is None:
        raise HTTPException(503, request.app.state.analyst_problem or "Analyse is not set up.")
    goal = Goal(body.goal_amount, body.goal_months, (body.goal_label or "").strip() or None) if body.goal_amount else None
    try:
        result = analyse(
            body.question,
            db_path=request.app.state.db_path,
            chat=chat,
            ask_llm=request.app.state.llm,
            session_factory=request.app.state.session_factory,
            goal=goal,
        )
    except LLMError as exc:
        raise HTTPException(502, str(exc)) from exc
    return result.to_dict()
