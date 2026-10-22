"""Deterministic catalog rules, independent of FastAPI and database queries.

Pairwise checks can later be reused by AC-3. Total power and build completeness
are build-wide checks and must also be run after selecting a configuration.
"""

from dataclasses import dataclass
from itertools import combinations
from typing import TypeVar

from app.compatibility_schemas import CompatibilityIssue, CompatibilityResult
from app.db.models import (
    Base, CaseSpec, Category, Component, CoolerSpec, CpuSpec, GpuSpec,
    MotherboardSpec, PsuSpec, RamSpec, StorageSpec,
)


@dataclass(frozen=True)
class SelectedPart:
    component: Component
    spec: Base | None


Spec = TypeVar("Spec", bound=Base)


def _spec(parts: dict[Category, SelectedPart], category: Category, cls: type[Spec]) -> Spec | None:
    part = parts.get(category)
    return part.spec if part is not None and isinstance(part.spec, cls) else None


LIMITATIONS = [
    "Results cover the rules supported by the manually entered catalog, not a guarantee of assembly.",
    "Motherboard CPU support lists and BIOS versions are not modeled; matching sockets alone are insufficient.",
    "Exact radiator mounts, radiator/GPU interference, RAM/cooler clearance, drive bays, and GPU slot clearance are not modeled.",
    "PSU cable counts, adapters, motherboard display outputs, and exact M.2 protocols/lengths are not fully modeled.",
    "Power uses selected parts' recorded peak draw; 20% headroom is an MVP policy, not a measurement or hardware standard.",
]


class RuleReport:
    def __init__(self, parts: dict[Category, SelectedPart]):
        self.parts = parts
        self.issues: list[CompatibilityIssue] = []
        self.checked: list[str] = []
        self.unknown = False

    def issue(self, code: str, message: str, *categories: Category, severity="error"):
        self.issues.append(CompatibilityIssue(
            code=code, severity=severity, message=message,
            component_ids=[self.parts[c].component.id for c in categories if c in self.parts],
        ))

    def check(self, code: str, condition: bool, message: str, *categories: Category):
        self.checked.append(code)
        if not condition:
            self.issue(code, message, *categories)

    def unverified(self, code: str, message: str, *categories: Category):
        self.unknown = True
        self.issue(code, message, *categories, severity="warning")


def _pair_report(parts: dict[Category, SelectedPart]) -> RuleReport:
    report = RuleReport(parts)
    cpu = _spec(parts, Category.CPU, CpuSpec)
    board = _spec(parts, Category.MOTHERBOARD, MotherboardSpec)
    ram = _spec(parts, Category.RAM, RamSpec)
    gpu = _spec(parts, Category.GPU, GpuSpec)
    storage = _spec(parts, Category.STORAGE, StorageSpec)
    psu = _spec(parts, Category.PSU, PsuSpec)
    case = _spec(parts, Category.CASE, CaseSpec)
    cooler = _spec(parts, Category.COOLER, CoolerSpec)

    if cpu and board:
        if not cpu.socket.strip() or not board.socket.strip():
            report.unverified("platform_socket_unknown", "CPU or motherboard socket is blank.",
                              Category.CPU, Category.MOTHERBOARD)
        else:
            report.check("cpu_socket", cpu.socket == board.socket,
                         f"CPU socket {cpu.socket} does not match motherboard socket {board.socket}.",
                         Category.CPU, Category.MOTHERBOARD)
        if cpu.memory_types:
            report.check("cpu_board_memory", board.memory_type in cpu.memory_types,
                         f"CPU supports {', '.join(cpu.memory_types)}, but the motherboard uses {board.memory_type}.",
                         Category.CPU, Category.MOTHERBOARD)
        else:
            report.unverified("cpu_memory_unknown", "CPU supported memory types are missing.", Category.CPU)

    if cpu and ram:
        if cpu.memory_types:
            report.check("cpu_ram_memory", ram.memory_type in cpu.memory_types,
                         f"CPU supports {', '.join(cpu.memory_types)}, but RAM uses {ram.memory_type}.",
                         Category.CPU, Category.RAM)
        else:
            report.unverified("cpu_memory_unknown", "CPU supported memory types are missing.", Category.CPU)

    if board and ram:
        report.check("board_ram_memory", board.memory_type == ram.memory_type,
                     f"Motherboard uses {board.memory_type}, but RAM uses {ram.memory_type}.",
                     Category.MOTHERBOARD, Category.RAM)
        report.check("ram_slots", ram.modules <= board.memory_slots,
                     f"RAM kit needs {ram.modules} slots; motherboard has {board.memory_slots}.",
                     Category.MOTHERBOARD, Category.RAM)
        report.check("ram_capacity", ram.capacity_gb <= board.max_memory_gb,
                     f"RAM kit has {ram.capacity_gb} GB; motherboard supports at most {board.max_memory_gb} GB.",
                     Category.MOTHERBOARD, Category.RAM)

    if board and case:
        if case.supported_board_form_factors:
            report.check("board_case_size", board.form_factor in case.supported_board_form_factors,
                         f"Case does not list support for {board.form_factor} motherboards.",
                         Category.MOTHERBOARD, Category.CASE)
        else:
            report.unverified("case_board_sizes_unknown", "Case supported motherboard sizes are missing.", Category.CASE)

    if gpu and case:
        report.check("gpu_length", gpu.length_mm <= case.max_gpu_length_mm,
                     f"GPU length is {gpu.length_mm} mm; case limit is {case.max_gpu_length_mm} mm.",
                     Category.GPU, Category.CASE)

    if psu and case:
        if psu.form_factor != case.psu_form_factor:
            # An adapter may make a smaller PSU fit; do not invent a hard conflict.
            report.unverified("psu_case_size", f"PSU is {psu.form_factor}; case lists {case.psu_form_factor}. Verify fit and any required adapter.",
                              Category.PSU, Category.CASE)
        else:
            report.checked.append("psu_case_size")

    if cpu and cooler:
        if not cpu.socket.strip():
            report.unverified("cpu_socket_unknown", "CPU socket is blank; cooler socket support cannot be checked.", Category.CPU)
        elif cooler.supported_sockets:
            report.check("cooler_socket", cpu.socket in cooler.supported_sockets,
                         f"Cooler does not list support for CPU socket {cpu.socket}.",
                         Category.CPU, Category.COOLER)
        else:
            report.unverified("cooler_sockets_unknown", "Cooler supported sockets are missing.", Category.COOLER)
        if cooler.max_tdp_w is None:
            report.issue("cooler_rating_unknown", "Cooler thermal rating is missing; verify cooling capacity manually.",
                         Category.CPU, Category.COOLER, severity="warning")
        elif cooler.max_tdp_w < cpu.tdp_w:
            report.issue("cooler_thermal_rating", f"Cooler rating is {cooler.max_tdp_w} W versus CPU TDP {cpu.tdp_w} W. Verify cooling capacity; ratings are approximate.",
                         Category.CPU, Category.COOLER, severity="warning")

    if cooler and case:
        if cooler.cooler_type == "air":
            if cooler.height_mm is None:
                report.unverified("cooler_height_unknown", "Air cooler height is missing.", Category.COOLER)
            else:
                report.check("cooler_height", cooler.height_mm <= case.max_cooler_height_mm,
                             f"Cooler height is {cooler.height_mm} mm; case limit is {case.max_cooler_height_mm} mm.",
                             Category.COOLER, Category.CASE)
        elif cooler.cooler_type == "aio":
            if cooler.radiator_mm is None:
                report.unverified("radiator_size_unknown", "AIO radiator size is missing.", Category.COOLER)
            elif case.max_radiator_mm is None:
                # The existing catalog defines NULL as no radiator support.
                report.check("case_radiator_unsupported", False,
                             "Case is recorded as having no AIO radiator support.",
                             Category.COOLER, Category.CASE)
            elif cooler.radiator_mm > case.max_radiator_mm:
                report.check("radiator_size", False,
                             f"Radiator is {cooler.radiator_mm} mm; case maximum is {case.max_radiator_mm} mm.",
                             Category.COOLER, Category.CASE)
            else:
                report.unverified("radiator_mounts_unverified", "Radiator is within the recorded maximum, but exact mounting sizes and clearance are not recorded.",
                                  Category.COOLER, Category.CASE)

    if board and storage:
        if storage.storage_type == "nvme" and storage.form_factor.startswith("M.2"):
            report.check("storage_m2_slot", board.m2_slots >= 1,
                         "Selected NVMe storage needs an M.2 slot; motherboard lists none.",
                         Category.MOTHERBOARD, Category.STORAGE)
        elif storage.storage_type == "nvme":
            report.unverified("storage_interface_unknown", "Non-M.2 NVMe connection support is not recorded on the motherboard.",
                              Category.MOTHERBOARD, Category.STORAGE)
        elif storage.form_factor.startswith("M.2"):
            report.check("storage_m2_slot", board.m2_slots >= 1,
                         "Selected M.2 storage needs an M.2 slot; motherboard lists none.",
                         Category.MOTHERBOARD, Category.STORAGE)
            report.unverified("storage_m2_sata_protocol", "M.2 SATA storage requires explicit SATA support on the M.2 slot; this is not recorded.",
                              Category.MOTHERBOARD, Category.STORAGE)
        else:
            report.check("storage_sata_port", board.sata_ports >= 1,
                         "Selected SATA storage needs a SATA port; motherboard lists none.",
                         Category.MOTHERBOARD, Category.STORAGE)

    if gpu and psu:
        report.issue("gpu_power_cables_unverified", "Verify GPU power connector types, cable counts, and adapters against the PSU; catalog data is insufficient for a complete cable check.",
                     Category.GPU, Category.PSU, severity="warning")

    return report


def check_pair(left: SelectedPart, right: SelectedPart) -> tuple[list[str], list[CompatibilityIssue], bool]:
    """Evaluate binary constraints without I/O, suitable for later AC-3 filtering.

    The final bool indicates missing data: such a pair must not be pruned as if
    it were a proven conflict. The AC-3 service uses these binary checks.
    """
    report = _pair_report({left.component.category: left, right.component.category: right})
    report.unknown |= left.spec is None or right.spec is None
    return report.checked, report.issues, report.unknown


def check_build(parts: dict[Category, SelectedPart]) -> CompatibilityResult:
    report = RuleReport(parts)
    for category in Category:
        if category not in parts:
            continue
        part = parts[category]
        if part.spec is None:
            report.unverified("specifications_missing", f"Specifications for {category.value} are missing; related rules could not be checked.", category)

    # Fixed category order gives repeatable reports regardless of JSON key order.
    ordered = [parts[category] for category in Category if category in parts]
    for left, right in combinations(ordered, 2):
        checked, issues, unknown = check_pair(left, right)
        report.checked.extend(checked)
        report.issues.extend(issues)
        report.unknown |= unknown

    required = {Category.CPU, Category.MOTHERBOARD, Category.RAM,
                Category.STORAGE, Category.PSU, Category.CASE}
    cpu = _spec(parts, Category.CPU, CpuSpec)
    if cpu:
        if not cpu.integrated_graphics:
            required.add(Category.GPU)
        if not cpu.includes_cooler:
            required.add(Category.COOLER)
    missing = [category for category in Category if category in required and category not in parts]

    # PSU wattage is capacity, not consumption. Selected parts only: a partial
    # build's estimate is a lower bound, not an estimate for a finished PC.
    draw = sum(part.component.power_draw_w for category, part in parts.items() if category != Category.PSU)
    recommended = (draw * 120 + 99) // 100
    gpu = _spec(parts, Category.GPU, GpuSpec)
    psu = _spec(parts, Category.PSU, PsuSpec)
    if gpu:
        recommended = max(recommended, gpu.recommended_psu_w)
    if psu:
        report.check("psu_capacity", psu.wattage >= draw,
                     f"Selected parts total {draw} W; PSU capacity is {psu.wattage} W.",
                     *[category for category in Category if category in parts])
        if draw <= psu.wattage < recommended:
            report.issue("psu_headroom", f"PSU provides {psu.wattage} W; recommended capacity for the selected parts is at least {recommended} W (20% margin and GPU recommendation).",
                         Category.PSU, severity="warning")

    # A known conflict takes precedence even in a partial or uncertain build.
    if any(issue.severity == "error" for issue in report.issues):
        status = "incompatible"
    elif missing:
        status = "incomplete"
    elif report.unknown:
        status = "undetermined"
    else:
        status = "compatible"

    # The same unknown CPU-memory field may be encountered by two binary rules.
    unique_issues = list({(issue.code, tuple(issue.component_ids)): issue for issue in report.issues}.values())
    return CompatibilityResult(
        status=status, missing_categories=missing, issues=unique_issues,
        checked_rules=list(dict.fromkeys(report.checked)), estimated_power_w=draw,
        recommended_psu_w=recommended, limitations=list(LIMITATIONS),
    )
