from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.models import Category


class CompatibilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    components: dict[Category, Annotated[int, Field(strict=True, gt=0)]] = Field(
        min_length=1, max_length=8,
        description="One catalog component ID per category; partial builds are allowed.",
    )

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.components.values())) != len(self.components):
            raise ValueError("Each component ID can only be selected once")
        return self


class CompatibilityIssue(BaseModel):
    code: str
    severity: Literal["error", "warning"]
    component_ids: list[int]
    message: str


class CompatibilityResult(BaseModel):
    status: Literal["compatible", "incompatible", "incomplete", "undetermined"]
    missing_categories: list[Category]
    issues: list[CompatibilityIssue]
    checked_rules: list[str]
    estimated_power_w: int
    recommended_psu_w: int
    limitations: list[str]


class FilterRequest(CompatibilityRequest):
    components: dict[Category, Annotated[int, Field(strict=True, gt=0)]] = Field(
        default_factory=dict, max_length=8,
        description="Fixed selections; omit to filter the whole catalog.",
    )


class FilterResult(BaseModel):
    status: Literal["arc_consistent", "inconsistent"]
    domains: dict[Category, list[int | None]]
    removed: dict[Category, list[int]]
    empty_categories: list[Category]
    limitations: list[str]
