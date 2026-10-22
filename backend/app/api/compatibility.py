from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.compatibility_schemas import CompatibilityRequest, CompatibilityResult
from app.db.models import Component, SPEC_MODELS
from app.db.session import get_db
from app.services.compatibility import SelectedPart, check_build

router = APIRouter(tags=["Compatibility"])


@router.post("/compatibility/check", response_model=CompatibilityResult)
def check_compatibility(payload: CompatibilityRequest, db: Annotated[Session, Depends(get_db)]):
    ids = list(payload.components.values())
    components = {component.id: component for component in db.scalars(
        select(Component).where(Component.id.in_(ids))
    )}
    missing = sorted(set(ids) - components.keys())
    if missing:
        raise HTTPException(status_code=404, detail={
            "message": "Components not found", "component_ids": missing,
        })
    mismatches = [
        {"component_id": component_id, "expected": category.value,
         "actual": components[component_id].category.value}
        for category, component_id in payload.components.items()
        if components[component_id].category != category
    ]
    if mismatches:
        raise HTTPException(status_code=422, detail={
            "message": "Component category mismatch", "mismatches": mismatches,
        })
    parts = {
        category: SelectedPart(components[component_id], db.get(SPEC_MODELS[category], component_id))
        for category, component_id in payload.components.items()
    }
    return check_build(parts)
