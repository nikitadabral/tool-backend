import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from app.schemas.brief import StructuredBrief
from app.services.ai_service import generate_structured_brief

SAMPLES_PATH = Path(__file__).with_name("samples.json")
REQUIRED_FIELDS = {
    "problem_summary",
    "likely_users",
    "solution_type",
    "clarifying_questions",
    "risks",
    "next_action",
}
FAILURE_MARKERS = (
    "generation failed",
    "provider failed",
    "unable to generate",
    "placeholder",
    "lorem ipsum",
    "todo",
)
CHECK_NAMES = (
    "generation_succeeded",
    "required_fields_present",
    "non_empty",
    "input_reflected",
    "reasonable_length",
    "no_failure_markers",
)
MIN_OUTPUT_LENGTH = 250
MAX_OUTPUT_LENGTH = 4_000


def load_samples(path: Path = SAMPLES_PATH) -> list[dict[str, Any]]:
    """Load the fixed evaluation dataset."""
    return json.loads(path.read_text(encoding="utf-8"))


def _check(passed: bool, details: str) -> dict[str, bool | str]:
    return {"passed": passed, "details": details}


def validate_brief(
    sample: dict[str, Any], brief: StructuredBrief
) -> dict[str, dict[str, bool | str]]:
    """Run deterministic, explainable quality checks against one brief."""
    data = brief.model_dump()
    output_text = json.dumps(data, ensure_ascii=True)
    normalized_output = output_text.casefold()
    missing_fields = sorted(REQUIRED_FIELDS - data.keys())
    empty_fields = sorted(
        field
        for field in REQUIRED_FIELDS
        if field in data and (not data[field] or not str(data[field]).strip())
    )
    missing_terms = [
        term
        for term in sample["required_terms"]
        if term.casefold() not in normalized_output
    ]
    found_markers = [
        marker for marker in FAILURE_MARKERS if marker in normalized_output
    ]
    output_length = len(output_text)

    return {
        "generation_succeeded": _check(True, "Brief generation completed."),
        "required_fields_present": _check(
            not missing_fields,
            "All required fields are present."
            if not missing_fields
            else f"Missing fields: {', '.join(missing_fields)}",
        ),
        "non_empty": _check(
            not empty_fields,
            "All required fields contain content."
            if not empty_fields
            else f"Empty fields: {', '.join(empty_fields)}",
        ),
        "input_reflected": _check(
            not missing_terms,
            "All expected input concepts are reflected."
            if not missing_terms
            else f"Missing expected terms: {', '.join(missing_terms)}",
        ),
        "reasonable_length": _check(
            MIN_OUTPUT_LENGTH <= output_length <= MAX_OUTPUT_LENGTH,
            f"Serialized brief length is {output_length} characters; expected "
            f"{MIN_OUTPUT_LENGTH}-{MAX_OUTPUT_LENGTH}.",
        ),
        "no_failure_markers": _check(
            not found_markers,
            "No failure or placeholder markers found."
            if not found_markers
            else f"Found failure markers: {', '.join(found_markers)}",
        ),
    }


def evaluate_sample(
    sample: dict[str, Any],
    generator: Callable[[str], StructuredBrief] = generate_structured_brief,
) -> dict[str, Any]:
    """Generate and evaluate one sample without propagating provider failures."""
    try:
        brief = generator(sample["request_text"])
        validations = validate_brief(sample, brief)
        generated_brief = brief.model_dump()
    except Exception as exc:
        reason = f"Generation failed: {type(exc).__name__}: {exc}"
        validations = {
            name: _check(False, reason if name == "generation_succeeded" else "Not evaluated because generation failed.")
            for name in CHECK_NAMES
        }
        generated_brief = None

    failure_details = [
        result["details"]
        for result in validations.values()
        if not result["passed"]
    ]
    return {
        "sample_id": sample["id"],
        "validations": validations,
        "overall_pass": not failure_details,
        "generated_brief": generated_brief,
        "failure_details": failure_details,
    }


def evaluate_samples(
    samples: list[dict[str, Any]],
    generator: Callable[[str], StructuredBrief] = generate_structured_brief,
) -> dict[str, Any]:
    """Evaluate all samples and calculate aggregate pass statistics."""
    results = [evaluate_sample(sample, generator) for sample in samples]
    passed = sum(result["overall_pass"] for result in results)
    total = len(results)
    failed = total - passed
    return {
        "results": results,
        "summary": {
            "total_samples": total,
            "passed": passed,
            "failed": failed,
            "pass_percentage": round((passed / total * 100) if total else 0, 1),
        },
    }


def main() -> int:
    report = evaluate_samples(load_samples())
    print(json.dumps(report, indent=2, ensure_ascii=True))
    return 0 if report["summary"]["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())