from dataclasses import dataclass
from typing import Protocol

from pydantic import ValidationError

from app.schemas.brief import StructuredBrief


class AIProvider(Protocol):
    """Provider contract for converting raw request text into a business brief."""

    def generate_structured_brief(self, request_text: str) -> object: ...


class AIOutputValidationError(Exception):
    """Raised when a provider returns data outside the brief contract."""


class AIGenerationError(Exception):
    """Raised when a provider cannot generate a response."""


@dataclass(frozen=True)
class BriefRule:
    signals: tuple[str, ...]
    problem_summary: str
    solution_type: str
    likely_users: tuple[str, ...]
    clarifying_question: str
    risk: str
    next_action: str


_BRIEF_RULES = (
    BriefRule(
        signals=(
            "health insurance",
            "health plan",
            "enrollment",
            "coverage",
            "benefits",
            "compare plans",
        ),
        problem_summary=(
            "Employees need a clear way to compare health plan coverage, costs, "
            "and benefits, while HR needs to reduce repetitive enrollment questions."
        ),
        solution_type="Benefits comparison and decision-support portal",
        likely_users=("Employees selecting benefits", "HR benefits teams"),
        clarifying_question=(
            "Which plan attributes, employee scenarios, and decision guidance must be compared?"
        ),
        risk="Plan details and eligibility rules may become outdated between enrollment cycles.",
        next_action="Normalize the available plan data and validate comparison criteria with HR.",
    ),
    BriefRule(
        signals=(
            "sales performance",
            "sales manager",
            "performance against targets",
            "excel files",
            "sales",
            "targets",
        ),
        problem_summary=(
            "Sales leaders need a centralized, timely view of performance against "
            "targets without manually consolidating team spreadsheets."
        ),
        solution_type="Sales performance analytics dashboard",
        likely_users=("Sales managers", "Sales operations analysts"),
        clarifying_question=(
            "Which source files, performance metrics, targets, and refresh frequency are required?"
        ),
        risk="Metric definitions and spreadsheet formats may differ across sales teams.",
        next_action="Inventory the source files and agree on shared sales metric definitions.",
    ),
    BriefRule(
        signals=(
            "support agents",
            "order status",
            "delivery dates",
            "refunds",
            "returns",
            "repetitive questions",
        ),
        problem_summary=(
            "Customers need fast, consistent answers to common order, delivery, refund, "
            "and return questions without depending on a support agent."
        ),
        solution_type="Customer self-service and support automation",
        likely_users=("Customers", "Customer support agents"),
        clarifying_question=(
            "Which support intents can be automated and which systems hold authoritative answers?"
        ),
        risk="Incorrect or stale automated answers could increase escalations and customer frustration.",
        next_action="Analyze top support intents and validate order and returns data integrations.",
    ),
    BriefRule(
        signals=(
            "vendor invoices",
            "vendor invoice",
            "scanned documents",
            "extract information",
            "invoice data",
            "finance system",
        ),
        problem_summary=(
            "Finance needs to capture vendor invoice data from mixed document formats "
            "with less manual entry, delay, and error."
        ),
        solution_type="Intelligent invoice processing automation",
        likely_users=("Accounts payable specialists", "Finance operations teams"),
        clarifying_question=(
            "Which invoice fields, validation rules, document formats, and finance integrations are required?"
        ),
        risk="Low-quality scans and inconsistent invoice layouts may reduce extraction accuracy.",
        next_action="Collect representative invoices and benchmark extraction against required fields.",
    ),
    BriefRule(
        signals=(
            "new employees",
            "employee onboarding",
            "onboarding activities",
            "policy acknowledgements",
            "training",
            "system access",
        ),
        problem_summary=(
            "HR and hiring teams need one view of onboarding tasks, ownership, and completion "
            "across training, documentation, access, and policy systems."
        ),
        solution_type="Employee onboarding workflow and tracking",
        likely_users=("New employees", "HR and hiring managers"),
        clarifying_question=(
            "Which onboarding tasks, owners, dependencies, deadlines, and systems must be tracked?"
        ),
        risk="Incomplete system integrations may leave the central completion status unreliable.",
        next_action="Map the onboarding journey and define a common task and completion model.",
    ),
    BriefRule(
        signals=(
            "travel expenses",
            "expense reports",
            "receipts",
            "reimbursements",
            "expense reimbursement",
            "pending reimbursements",
        ),
        problem_summary=(
            "Employees and Finance need a structured expense submission and review process "
            "with complete information and visible reimbursement status."
        ),
        solution_type="Travel expense workflow and reimbursement tracking",
        likely_users=("Employees submitting expenses", "Finance reviewers"),
        clarifying_question=(
            "Which receipt fields, policy checks, approval levels, and exception paths are required?"
        ),
        risk="Missing evidence or unclear policy rules may continue to delay reimbursements.",
        next_action="Map the expense workflow and define required fields and approval rules.",
    ),
    BriefRule(
        signals=(
            "application access",
            "request access",
            "access requests",
            "emails to it",
            "missing information",
            "it has to",
        ),
        problem_summary=(
            "IT needs complete, consistently routed application-access requests to reduce "
            "email follow-up and processing delays."
        ),
        solution_type="Application access request workflow",
        likely_users=("Employees requesting access", "IT access administrators"),
        clarifying_question=(
            "Which applications, roles, required request fields, and approval paths are in scope?"
        ),
        risk="Weak approval and entitlement controls could grant excessive or inappropriate access.",
        next_action="Define an application catalog, required fields, and role-based approval routing.",
    ),
    BriefRule(
        signals=(
            "marketing campaign",
            "campaign data",
            "social media",
            "search platforms",
            "campaign performance",
            "marketing analysts",
        ),
        problem_summary=(
            "Marketing needs a consolidated cross-channel view of campaign performance "
            "without manually combining platform data."
        ),
        solution_type="Cross-channel marketing analytics dashboard",
        likely_users=("Marketing analysts", "Campaign managers"),
        clarifying_question=(
            "Which channels, campaign identifiers, metrics, attribution rules, and refresh cadence are required?"
        ),
        risk="Inconsistent attribution and campaign naming may produce misleading comparisons.",
        next_action="Inventory channel APIs and establish shared campaign and attribution definitions.",
    ),
    BriefRule(
        signals=(
            "office issues",
            "broken equipment",
            "temperature problems",
            "cleaning requirements",
            "meeting-room",
            "facilities",
        ),
        problem_summary=(
            "Facilities needs one intake and tracking process for workplace issues submitted "
            "through different channels."
        ),
        solution_type="Facilities service request management",
        likely_users=("Employees reporting workplace issues", "Facilities teams"),
        clarifying_question=(
            "Which issue categories, locations, service levels, routing rules, and status updates are required?"
        ),
        risk="Unclear ownership and duplicate reports may distort workload and resolution status.",
        next_action="Create a facilities service catalog with routing and service-level rules.",
    ),
    BriefRule(
        signals=(
            "customer requests",
            "email, chat",
            "different teams",
            "teams are overloaded",
            "workload visibility",
            "resolution",
            "how long requests take",
        ),
        problem_summary=(
            "Management needs a unified view of customer demand, resolution time, and team "
            "capacity across fragmented intake channels."
        ),
        solution_type="Omnichannel customer request management and analytics",
        likely_users=("Customer operations leaders", "Service team managers"),
        clarifying_question=(
            "Which channels, request categories, ownership rules, service levels, and capacity metrics are needed?"
        ),
        risk="Duplicate requests and inconsistent categorization may undermine workload reporting.",
        next_action="Sample demand across channels and define a shared request taxonomy and ownership model.",
    ),
    BriefRule(
        signals=("report", "dashboard", "metric"),
        problem_summary=(
            "Business teams need a consistent view of operational information and performance metrics."
        ),
        solution_type="Reporting and analytics solution",
        likely_users=("Business analysts", "Operational leaders"),
        clarifying_question="Which metrics and source systems must the solution include?",
        risk="Metric definitions may differ across source systems.",
        next_action="Confirm priority metrics, owners, and authoritative source systems.",
    ),
    BriefRule(
        signals=("manual", "automate", "workflow"),
        problem_summary=(
            "A manual business process needs clearer workflow, ownership, and automation."
        ),
        solution_type="Workflow automation",
        likely_users=("Process operators", "Business operations team"),
        clarifying_question="Which workflow steps require human approval?",
        risk="Automation may encode an incomplete or changing process.",
        next_action="Document the current workflow, exceptions, and approval controls.",
    ),
    BriefRule(
        signals=("customer", "member", "client"),
        problem_summary=(
            "Customer-facing teams need a more consistent way to support the target journey."
        ),
        solution_type="Customer experience solution",
        likely_users=("Customer service teams", "Customers or members"),
        clarifying_question="Which customer journey and channels are in scope?",
        risk="Customer data handling requirements need validation.",
        next_action="Map the target customer journey and confirm data-handling requirements.",
    ),
)


_DEFAULT_RULE = BriefRule(
    signals=(),
    problem_summary="The request needs further discovery to define the business problem and target outcome.",
    solution_type="Business process improvement",
    likely_users=("Requesting business team", "Operational stakeholders"),
    clarifying_question="Which teams and systems are affected by the current process?",
    risk="Dependencies on existing systems have not yet been assessed.",
    next_action="Schedule discovery with the requester and key operational stakeholders.",
)


def _rule_score(rule: BriefRule, text: str) -> int:
    return sum(len(signal.split()) for signal in rule.signals if signal in text)


class MockAIProvider:
    """Deterministic local provider that scores domain signals in request text."""

    def generate_structured_brief(self, request_text: str) -> object:
        normalized_text = " ".join(request_text.split())
        lowered = normalized_text.lower()
        rule = max(_BRIEF_RULES, key=lambda item: _rule_score(item, lowered))
        if _rule_score(rule, lowered) == 0:
            rule = _DEFAULT_RULE

        # TODO: Replace this heuristic with the real LLM call and prompt in an
        # OpenAIProvider implementing AIProvider; the API layer remains unchanged.
        return {
            "problem_summary": rule.problem_summary,
            "likely_users": list(rule.likely_users),
            "solution_type": rule.solution_type,
            "clarifying_questions": [
                "What outcome would define success for this request?",
                rule.clarifying_question,
            ],
            "risks": [
                "Requirements may change after stakeholder discovery.",
                rule.risk,
            ],
            "next_action": rule.next_action,
        }


_provider: AIProvider = MockAIProvider()


def generate_structured_brief(
    request_text: str, provider: AIProvider | None = None
) -> StructuredBrief:
    """Generate and validate a brief through the configured provider boundary."""
    try:
        output = (provider or _provider).generate_structured_brief(request_text)
    except Exception as exc:
        raise AIGenerationError("AI provider failed to generate a brief") from exc

    try:
        return StructuredBrief.model_validate(output)
    except ValidationError as exc:
        raise AIOutputValidationError("AI provider returned invalid output") from exc