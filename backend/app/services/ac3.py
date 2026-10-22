"""Arc consistency for catalog domains; absence is allowed for GPU and cooler."""
from collections import deque
from app.db.models import Category, CpuSpec
from app.services.compatibility import SelectedPart, check_pair


def supported(left_category, left, right_category, right):
    if left is None or right is None:
        absent, other = (left_category, right) if left is None else (right_category, left)
        if other is not None and isinstance(other.spec, CpuSpec):
            if absent == Category.GPU:
                return other.spec.integrated_graphics
            if absent == Category.COOLER:
                return other.spec.includes_cooler
        return True
    _, issues, _ = check_pair(left, right)
    return not any(issue.severity == "error" for issue in issues)


def filter_domains(domains):
    """Return copied domains after propagation; never mutate caller selections.

    Unknown specifications retain support. Nonempty domains do not prove that a
    complete solution exists; total power must be checked on the final build.
    """
    remaining = {category: list(values) for category, values in domains.items()}
    queue = deque((a, b) for a in remaining for b in remaining if a != b)
    queued = set(queue)
    cache = {}
    def compatible(a, x, b, y):
        key = (a, None if x is None else x.component.id,
               b, None if y is None else y.component.id)
        if key not in cache:
            cache[key] = supported(a, x, b, y)
        return cache[key]

    while queue:
        a, b = queue.popleft()
        queued.remove((a, b))
        revised = [x for x in remaining[a]
                   if any(compatible(a, x, b, y) for y in remaining[b])]
        if len(revised) != len(remaining[a]):
            remaining[a] = revised
            for neighbor in remaining:
                arc = (neighbor, a)
                if neighbor != a and neighbor != b and arc not in queued:
                    queue.append(arc)
                    queued.add(arc)
    return remaining
