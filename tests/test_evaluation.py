from app.schemas.brief import StructuredBrief
from evaluation.evaluate_briefs import (
    CHECK_NAMES,
    evaluate_samples,
    load_samples,
    validate_brief,
)


def make_brief(problem_summary: str = "A manual workflow needs improvement."):
    return StructuredBrief(
        problem_summary=problem_summary,
        likely_users=["Business users", "Operations team"],
        solution_type="Workflow automation and process tracking",
        clarifying_questions=[
            "Which workflow stages and business rules are required?",
            "What outcome will define success for the operations team?",
        ],
        risks=[
            "Requirements may change during stakeholder discovery.",
            "Existing system integrations need technical validation.",
        ],
        next_action="Document the workflow and validate it with business users.",
    )


def test_fixed_dataset_passes_through_application_generator():
    samples = load_samples()

    report = evaluate_samples(samples)

    assert 5 <= len(samples) <= 10
    assert len({sample["id"] for sample in samples}) == len(samples)
    assert report["summary"] == {
        "total_samples": 8,
        "passed": 8,
        "failed": 0,
        "pass_percentage": 100.0,
    }
    assert all(result["overall_pass"] for result in report["results"])
    assert all(result["generated_brief"] for result in report["results"])


def test_validation_failures_are_deterministic_and_explainable():
    sample = {
        "id": "missing-concepts",
        "request_text": "A request about invoices.",
        "required_terms": ["invoice"],
    }
    brief = make_brief("TODO: placeholder response")

    validations = validate_brief(sample, brief)

    assert validations["input_reflected"] == {
        "passed": False,
        "details": "Missing expected terms: invoice",
    }
    assert validations["no_failure_markers"]["passed"] is False
    assert "placeholder" in validations["no_failure_markers"]["details"]


def test_generation_failure_does_not_stop_remaining_samples():
    samples = [
        {"id": "provider-failure", "request_text": "Fail", "required_terms": []},
        {
            "id": "successful-sample",
            "request_text": "Improve this workflow",
            "required_terms": ["workflow"],
        },
    ]

    def generator(request_text: str) -> StructuredBrief:
        if request_text == "Fail":
            raise RuntimeError("provider unavailable")
        return make_brief()

    report = evaluate_samples(samples, generator)

    failed, passed = report["results"]
    assert failed["overall_pass"] is False
    assert failed["generated_brief"] is None
    assert set(failed["validations"]) == set(CHECK_NAMES)
    assert "provider unavailable" in failed["failure_details"][0]
    assert passed["overall_pass"] is True
    assert report["summary"] == {
        "total_samples": 2,
        "passed": 1,
        "failed": 1,
        "pass_percentage": 50.0,
    }