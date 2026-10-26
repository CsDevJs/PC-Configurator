"""Min-Cost Max-Flow by successive shortest paths, independent of the catalog.

Repeatedly finds the cheapest path from source to sink in the residual graph
with Bellman-Ford, then sends as much flow along it as the path allows.
Bellman-Ford handles the negative costs of reverse (residual) edges directly.
Each augmentation uses a cheapest possible path, so when no path is left the
flow is maximum and, among all maximum flows, has minimum total cost.

Costs and capacities are integers: callers convert prices to bani, which keeps
the result exact. Initial edge costs must be non-negative, so the residual graph
never has a negative cycle.
Complexity: O(F * V * E) for total flow F.
"""

from dataclasses import dataclass, field

INF = float("inf")


@dataclass
class MinCostMaxFlow:
    node_count: int
    # Edge i and edge i ^ 1 are each other's reverse (residual) edge.
    _from: list[int] = field(default_factory=list)
    _to: list[int] = field(default_factory=list)
    _cap: list[int] = field(default_factory=list)
    _cost: list[int] = field(default_factory=list)
    _original_cap: list[int] = field(default_factory=list)

    def add_edge(self, u: int, v: int, capacity: int, cost: int) -> int:
        """Add a directed edge and return its ID, for reading its flow later."""
        if capacity < 0 or cost < 0:
            raise ValueError("Capacity and cost must be non-negative")
        edge_id = len(self._to)
        for frm, to, cap, c in ((u, v, capacity, cost), (v, u, 0, -cost)):
            self._from.append(frm)
            self._to.append(to)
            self._cap.append(cap)
            self._cost.append(c)
            self._original_cap.append(cap)
        return edge_id

    def flow_on(self, edge_id: int) -> int:
        return self._original_cap[edge_id] - self._cap[edge_id]

    def solve(self, source: int, sink: int) -> tuple[int, int]:
        """Push maximum flow at minimum cost. Returns (total flow, total cost)."""
        total_flow = total_cost = 0
        while True:
            dist, parent_edge = self._bellman_ford(source)
            if dist[sink] == INF:
                return total_flow, total_cost

            # Bottleneck along the path, then augment.
            push, node = INF, sink
            while node != source:
                edge = parent_edge[node]
                push = min(push, self._cap[edge])
                node = self._from[edge]
            node = sink
            while node != source:
                edge = parent_edge[node]
                self._cap[edge] -= push
                self._cap[edge ^ 1] += push
                node = self._from[edge]
            total_flow += push
            total_cost += push * dist[sink]

    def _bellman_ford(self, source: int) -> tuple[list[float], list[int]]:
        """Cheapest distance from source to every node over edges with spare capacity."""
        dist: list[float] = [INF] * self.node_count
        parent_edge = [-1] * self.node_count
        dist[source] = 0
        # At most V - 1 rounds of relaxing every edge; stop early once nothing changes.
        for _ in range(self.node_count - 1):
            changed = False
            for edge in range(len(self._to)):
                u = self._from[edge]
                if self._cap[edge] > 0 and dist[u] < INF and dist[u] + self._cost[edge] < dist[self._to[edge]]:
                    dist[self._to[edge]] = dist[u] + self._cost[edge]
                    parent_edge[self._to[edge]] = edge
                    changed = True
            if not changed:
                break
        return dist, parent_edge
