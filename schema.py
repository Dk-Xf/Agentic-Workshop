"""The triage decision schema: the single source of truth for Epics 2 and 3."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationInfo, field_validator

Category = Literal["billing", "bug", "access", "performance", "how-to"]
Priority = Literal["P1", "P2", "P3", "P4"]
Route = Literal["billing-team", "bug-team", "access-team", "performance-team", "how-to-team"]

ROUTE_FOR_CATEGORY: dict[str, str] = {
    "billing": "billing-team",
    "bug": "bug-team",
    "access": "access-team",
    "performance": "performance-team",
    "how-to": "how-to-team",
}


class TriageDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    priority: Priority
    route: Route
    rationale: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

    @field_validator("route")
    @classmethod
    def route_matches_category(cls, route: str, info: ValidationInfo) -> str:
        category = info.data.get("category")
        # If category failed validation it is absent here; that error is reported already.
        if category is not None and route != ROUTE_FOR_CATEGORY[category]:
            raise ValueError(
                f"route must be {ROUTE_FOR_CATEGORY[category]!r} for category {category!r}, got {route!r}"
            )
        return route
