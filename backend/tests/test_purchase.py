import itertools
import random
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import Availability, Component, Offer
from app.services.mcmf import MinCostMaxFlow
from app.services.purchase import StoreOffer, plan_purchase

D = Decimal


def offers(**prices):
    """offers(s1="100", s3="90") -> offers at store 1 and store 3."""
    return [StoreOffer(int(store[1:]), D(price)) for store, price in prices.items()]


# ---------- The generic solver ----------

def test_mcmf_prefers_cheaper_paths_and_reports_max_flow():
    # 0 -> 1 -> 3 costs 2 per unit (cap 2); 0 -> 2 -> 3 costs 5 per unit (cap 2).
    g = MinCostMaxFlow(4)
    a = g.add_edge(0, 1, 2, 1)
    g.add_edge(1, 3, 2, 1)
    b = g.add_edge(0, 2, 2, 2)
    g.add_edge(2, 3, 2, 3)
    assert g.solve(0, 3) == (4, 2 * 2 + 2 * 5)
    assert (g.flow_on(a), g.flow_on(b)) == (2, 2)


def test_mcmf_reroutes_through_reverse_edges():
    # The first cheapest path 0-1-2-3 blocks both other paths; reaching the
    # maximum flow of 2 needs the second path to cancel flow on 1->2.
    g = MinCostMaxFlow(4)
    g.add_edge(0, 1, 1, 0)
    g.add_edge(0, 2, 1, 5)
    g.add_edge(1, 2, 1, 0)
    g.add_edge(1, 3, 1, 5)
    g.add_edge(2, 3, 1, 0)
    assert g.solve(0, 3) == (2, 10)


def test_mcmf_rejects_negative_inputs():
    g = MinCostMaxFlow(2)
    with pytest.raises(ValueError):
        g.add_edge(0, 1, -1, 0)
    with pytest.raises(ValueError):
        g.add_edge(0, 1, 1, -1)


def brute_force_flow(node_count, edges, source, sink):
    """Max flow, then min cost, by trying every integer flow on small unit graphs."""
    best = (0, 0)
    for flows in itertools.product(*[range(cap + 1) for _, _, cap, _ in edges]):
        balance = [0] * node_count
        for (u, v, _, _), f in zip(edges, flows):
            balance[u] -= f
            balance[v] += f
        if any(balance[n] for n in range(node_count) if n not in (source, sink)):
            continue
        cost = sum(f * c for (_, _, _, c), f in zip(edges, flows))
        if (balance[sink], -cost) > (best[0], -best[1]):
            best = (balance[sink], cost)
    return best


def test_mcmf_matches_brute_force_on_random_graphs():
    rng = random.Random(7)
    for _ in range(300):
        n = rng.randint(2, 5)
        edges = [(u, v, rng.randint(1, 2), rng.randint(0, 9))
                 for u in range(n) for v in range(n) if u != v and rng.random() < 0.4][:7]
        g = MinCostMaxFlow(n)
        for e in edges:
            g.add_edge(*e)
        assert g.solve(0, n - 1) == brute_force_flow(n, edges, 0, n - 1), edges


# ---------- The purchase planner ----------

def test_each_part_goes_to_its_cheapest_store():
    plan = plan_purchase({"cpu": offers(s1="3000", s2="2900"), "gpu": offers(s1="9000", s2="9500")})
    assert {k: a.store_id for k, a in plan.assignments.items()} == {"cpu": 2, "gpu": 1}
    assert plan.total == D("11900.00") and plan.max_flow == 2 and plan.unassigned == []


def test_equal_prices_go_to_lower_store_id():
    plan = plan_purchase({"ram": offers(s3="500", s2="500")})
    assert plan.assignments["ram"].store_id == 2


def test_part_without_offers_is_reported_not_dropped():
    plan = plan_purchase({"cpu": offers(s1="100"), "case": []})
    assert plan.unassigned == ["case"]
    assert plan.max_flow == 1 and plan.total == D("100.00")


def test_prices_must_have_at_most_two_decimals():
    with pytest.raises(ValueError):
        plan_purchase({"a": [StoreOffer(1, D("1.005"))]})


def test_planner_matches_brute_force_on_random_cases():
    rng = random.Random(2026)
    for _ in range(500):
        stores = list(range(1, rng.randint(1, 4) + 1))
        parts = {
            f"p{i}": [StoreOffer(s, D(rng.randint(50, 600)) / 2) for s in stores if rng.random() < 0.75]
            for i in range(rng.randint(1, 6))
        }
        plan = plan_purchase(parts)
        best = [min(o.price for o in options) for options in parts.values() if options]
        assert plan.max_flow == len(best)
        assert plan.total == sum(best, D(0)).quantize(D("0.01"))
        for key, chosen in plan.assignments.items():
            assert chosen in parts[key]


# ---------- POST /purchase/plan ----------

def test_invalid_plan_requests(client):
    assert client.post("/purchase/plan", json={"components": {}}).status_code == 422
    assert client.post("/purchase/plan", json={"components": {"cpu": 1}, "store": "xstore"}).status_code == 422


def catalog_ids(db, *slugs):
    return [db.scalar(select(Component.id).where(Component.slug == s)) for s in slugs]


FULL_BUILD = ("amd-ryzen-5-7600", "gigabyte-b650m-d3hp", "kingston-kf560c36bbe2ak2-32",
              "gigabyte-rx-9060-xt-gaming-oc-16g", "samsung-990-evo-plus-1tb", "cougar-gex-pro-750",
              "deepcool-cc560-v2-black", "deepcool-ak620-digital")
CATEGORIES = ("cpu", "motherboard", "ram", "gpu", "storage", "psu", "case", "cooler")


def test_plan_buys_every_part_at_its_cheapest_store(catalog_client):
    client, db = catalog_client
    components = dict(zip(CATEGORIES, catalog_ids(db, *FULL_BUILD)))
    body = client.post("/purchase/plan", json={"components": components}).json()
    assert body["status"] == "complete" and body["unplanned"] == []
    assert [i["category"] for i in body["items"]] == list(CATEGORIES)
    for item in body["items"]:
        cheapest = min(o.price_mdl for o in db.scalars(select(Offer).where(
            Offer.component_id == item["component_id"], Offer.availability == Availability.IN_STOCK)))
        assert D(item["price_mdl"]) == cheapest
    assert D(body["total_mdl"]) == sum(D(i["price_mdl"]) for i in body["items"])
    assert D(body["total_mdl"]) == sum(D(s["subtotal_mdl"]) for s in body["stores"])
    assert sum(s["part_count"] for s in body["stores"]) == 8


def test_plan_reports_parts_nobody_has_in_stock(catalog_client):
    client, db = catalog_client
    cpu, board = catalog_ids(db, "intel-core-i3-12100f", "gigabyte-b760m-h-ddr4")
    for offer in db.scalars(select(Offer).where(Offer.component_id == cpu)):
        offer.availability = Availability.OUT_OF_STOCK
    db.flush()
    body = client.post("/purchase/plan", json={"components": {"cpu": cpu, "motherboard": board}}).json()
    assert body["status"] == "partial"
    assert body["unplanned"] == [{"category": "cpu", "component_id": cpu, "reason": "no_offer_in_stock"}]
    # The B760M H DDR4 is in stock only at Xstore in the seed data.
    assert [(i["category"], i["store"]["slug"]) for i in body["items"]] == [("motherboard", "xstore")]


def test_plan_unknown_component(catalog_client):
    client, _ = catalog_client
    assert client.post("/purchase/plan", json={"components": {"cpu": 999999}}).status_code == 404
