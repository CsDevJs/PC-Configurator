"""Choose which store to buy each part from, using Min-Cost Max-Flow.

Network (one unit of flow = one part bought):

    source ──1──▶ part ──1, price──▶ store ──▶ sink

- source → part: capacity 1, each part is bought once.
- part → store: one edge per in-stock offer, cost = price in bani.
- store → sink: enough capacity for every part.

Max flow = how many parts can be bought at all. Min cost = the cheapest way to
buy them.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Hashable

from app.services.mcmf import MinCostMaxFlow


@dataclass(frozen=True)
class StoreOffer:
    store_id: int
    price: Decimal


@dataclass(frozen=True)
class PurchasePlan:
    assignments: dict[Hashable, StoreOffer]
    unassigned: list[Hashable]  # parts with no in-stock offer
    total: Decimal
    max_flow: int


def _bani(price: Decimal) -> int:
    bani = price * 100
    if bani != bani.to_integral_value():
        raise ValueError(f"Price {price} has more than 2 decimals")
    return int(bani)


def plan_purchase(parts: dict[Hashable, list[StoreOffer]]) -> PurchasePlan:
    """Buy as many parts as possible, as cheaply as possible.

    `parts` maps any part key (e.g. a category) to its purchasable offers.
    Ties between equal prices go to the lower store ID, so results are stable.
    """
    keys = list(parts)
    store_ids = sorted({o.store_id for offers in parts.values() for o in offers})
    # Encode cost = bani * tie + store rank. tie exceeds any possible sum of ranks,
    # so rank only breaks ties and total_cost // tie is exactly the total in bani.
    tie = len(keys) * max(len(store_ids), 1) + 1
    rank = {store_id: i for i, store_id in enumerate(store_ids)}

    source, sink = 0, 1
    part_node = {key: 2 + i for i, key in enumerate(keys)}
    store_node = {sid: 2 + len(keys) + i for i, sid in enumerate(store_ids)}
    graph = MinCostMaxFlow(2 + len(keys) + len(store_ids))

    offer_edges: dict[Hashable, list[tuple[int, StoreOffer]]] = {}
    for key, offers in parts.items():
        graph.add_edge(source, part_node[key], 1, 0)
        offer_edges[key] = [
            (graph.add_edge(part_node[key], store_node[o.store_id], 1, _bani(o.price) * tie + rank[o.store_id]), o)
            for o in offers
        ]
    for sid in store_ids:
        graph.add_edge(store_node[sid], sink, len(keys), 0)

    max_flow, cost = graph.solve(source, sink)

    assignments: dict[Hashable, StoreOffer] = {}
    for key in keys:
        used = [offer for edge, offer in offer_edges[key] if graph.flow_on(edge)]
        if used:
            assignments[key] = used[0]
    unassigned = [key for key in keys if key not in assignments]
    total = Decimal(cost // tie) / 100
    return PurchasePlan(assignments, unassigned, total.quantize(Decimal("0.01")), max_flow)
