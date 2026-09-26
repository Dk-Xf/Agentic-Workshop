import json

import pytest
from pydantic import ValidationError

from schema import TriageDecision

VALID = {
    "category": "billing",
    "priority": "P2",
    "route": "billing-team",
    "rationale": "Double charge puts money at stake (P2).",
}


def make(**overrides) -> dict:
    data = {**VALID, **overrides}
    return {k: v for k, v in data.items() if v is not ...}


def assert_rejected(data: dict, field: str, *needles: str) -> None:
    """The error must be located at `field` (and only there) and mention each needle."""
    with pytest.raises(ValidationError) as exc:
        TriageDecision.model_validate(data)
    assert [e["loc"][0] for e in exc.value.errors()] == [field]
    for needle in needles:
        assert needle in str(exc.value)


def test_valid_decision_round_trips_json():
    raw = json.dumps(VALID)
    decision = TriageDecision.model_validate_json(raw)
    assert json.loads(decision.model_dump_json()) == VALID


def test_rationale_is_stripped():
    assert TriageDecision.model_validate(make(rationale="  x  ")).rationale == "x"


def test_bad_priority():
    assert_rejected(make(priority="P5"), "priority")


@pytest.mark.parametrize(
    "overrides,field",
    [({"category": "refund"}, "category"), ({"route": "sales-team"}, "route")],
)
def test_bad_category_or_route(overrides, field):
    assert_rejected(make(**overrides), field)


@pytest.mark.parametrize("field", ["category", "priority", "route", "rationale"])
def test_missing_field(field):
    assert_rejected(make(**{field: ...}), field)


def test_mismatched_route_names_field_and_expected_route():
    assert_rejected(make(route="bug-team"), "route", "billing-team")


def test_mismatched_route_for_another_category():
    assert_rejected(make(category="access", route="billing-team"), "route", "access-team")


def test_invalid_category_reports_only_category():
    assert_rejected(make(category="refund", route="bug-team"), "category")


def test_extra_field():
    assert_rejected(make(confidence=0.9), "confidence")


@pytest.mark.parametrize("rationale", ["", "   ", "\n\t "])
def test_empty_rationale(rationale):
    assert_rejected(make(rationale=rationale), "rationale")


@pytest.mark.parametrize("rationale", [None, 123, ["x"]])
def test_non_string_rationale(rationale):
    assert_rejected(make(rationale=rationale), "rationale")


@pytest.mark.parametrize(
    "category,route",
    [
        ("billing", "billing-team"),
        ("bug", "bug-team"),
        ("access", "access-team"),
        ("performance", "performance-team"),
        ("how-to", "how-to-team"),
    ],
)
def test_every_category_accepts_its_route(category, route):
    assert TriageDecision.model_validate(make(category=category, route=route)).route == route
