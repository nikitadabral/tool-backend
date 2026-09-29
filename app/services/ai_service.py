from typing import Protocol

from app.schemas.brief import StructuredBrief


class BriefProvider(Protocol):
    """Provider contract for converting raw request text into a business brief."""

    def generate(self, request_text: str) -> StructuredBrief: ...


class PlaceholderBriefProvider:
    """Deterministic placeholder to replace with an LLM-backed provider later."""

    def generate(self, request_text: str) -> StructuredBrief:
        normalized_text = " ".join(request_text.split())
        summary = normalized_text[:240]
        if len(normalized_text) > 240:
            summary = f"{summary.rstrip()}..."

        lowered = normalized_text.lower()
        if any(term in lowered for term in ("report", "dashboard", "metric")):
            solution_type = "Reporting and analytics solution"
        elif any(term in lowered for term in ("manual", "automate", "workflow")):
            solution_type = "Workflow automation"
        else:
            solution_type = "Business process improvement"

        return StructuredBrief(
            problem_summary=summary or "The request requires additional business context.",
            likely_users=["Requesting business team", "Operational stakeholders"],
            solution_type=solution_type,
            clarifying_questions=[
                "What outcome would define success for this request?",
                "Which teams and systems are affected by the current process?",
            ],
            risks=[
                "Requirements may change after stakeholder discovery.",
                "Dependencies on existing systems have not yet been assessed.",
            ],
            next_action="Schedule a discovery session with the requester and key stakeholders.",
        )


_provider: BriefProvider = PlaceholderBriefProvider()


def generate_structured_brief(request_text: str) -> StructuredBrief:
    """Generate a structured brief through the configured provider boundary."""
    return _provider.generate(request_text)