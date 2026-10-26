from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.builds import load_selection
from app.db.models import Availability
from app.db.session import get_db
from app.purchase_schemas import PlannedItem, PurchasePlanRead, PurchasePlanRequest, StoreSubtotal, UnplannedItem
from app.schemas import StoreRead
from app.services.purchase import StoreOffer, plan_purchase

router = APIRouter(tags=["Purchase planning"])


@router.post("/purchase/plan", response_model=PurchasePlanRead)
def purchase_plan(payload: PurchasePlanRequest, db: Annotated[Session, Depends(get_db)]) -> PurchasePlanRead:
    """Pick a store for every selected part at the lowest total price (Min-Cost Max-Flow).

    Only in-stock offers are used. Prices are as entered in the catalog; delivery
    fees are not modeled.
    """
    selection = load_selection(db, payload.components)
    in_stock = {category: [o for o in component.offers if o.availability == Availability.IN_STOCK]
                for category, component in selection.items()}
    plan = plan_purchase(
        {category: [StoreOffer(o.store_id, o.price_mdl) for o in offers] for category, offers in in_stock.items()}
    )

    items, subtotals, stores = [], {}, {}
    for category, chosen in plan.assignments.items():
        component = selection[category]
        offer = next(o for o in in_stock[category] if o.store_id == chosen.store_id)
        items.append(PlannedItem(
            category=category, component_id=component.id,
            component_name=f"{component.brand} {component.model}",
            store=StoreRead.model_validate(offer.store), price_mdl=offer.price_mdl, url=offer.url,
        ))
        stores[offer.store_id] = offer.store
        count, subtotal = subtotals.get(offer.store_id, (0, 0))
        subtotals[offer.store_id] = (count + 1, subtotal + offer.price_mdl)

    return PurchasePlanRead(
        status="complete" if not plan.unassigned else "partial",
        items=sorted(items, key=lambda i: list(selection).index(i.category)),
        unplanned=[UnplannedItem(category=c, component_id=selection[c].id, reason="no_offer_in_stock")
                   for c in plan.unassigned],
        stores=[StoreSubtotal(store=StoreRead.model_validate(stores[sid]), part_count=n, subtotal_mdl=s)
                for sid, (n, s) in sorted(subtotals.items(), key=lambda kv: -kv[1][1])],
        total_mdl=plan.total,
    )
