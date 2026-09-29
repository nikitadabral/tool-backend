from pydantic import BaseModel


class StructuredBrief(BaseModel):
    """Structured business context generated from an original request."""

    problem_summary: str
    likely_users: list[str]
    solution_type: str
    clarifying_questions: list[str]
    risks: list[str]
    next_action: str