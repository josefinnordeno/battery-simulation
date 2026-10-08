"""Finite, grid-aware charging controllers for interchangeable modules."""

from models import Battery


def allocate_charging(
    batteries: list[Battery],
    charger_count: int,
    power_kw: float,
    headroom_kw: float,
    *,
    policy: str = "immediate",
    deadlines: list[float] | None = None,
    current_minutes: float = 0,
    reserve_count: int = 0,
    reserve_target: int = 3,
) -> list[tuple[Battery, float]]:
    """Allocate grid-side power without exceeding ports or grid headroom.

    Immediate is FIFO. Deadline charging prioritizes shortest refill time and
    spreads charging to the next uncovered machine demand. Modules are shared,
    so predicted swap deadlines are assigned to charge jobs in completion order.
    A low reserve forces maximum-rate recovery. Dispatch may preempt each minute.
    """
    if policy not in {"immediate", "deadline"}:
        raise ValueError("Unknown charging policy")
    jobs = list(batteries)
    if policy == "deadline":
        jobs.sort(key=lambda b: (b.soc_max - b.soc) * b.capacity_kwh / b.charging_efficiency)
    allocation = []
    remaining = max(0.0, headroom_kw)
    due = deadlines or []
    for rank, battery in enumerate(jobs[:charger_count]):
        requested = power_kw
        if policy == "deadline" and reserve_count >= reserve_target:
            deadline_index = reserve_count + rank
            deadline = due[deadline_index] if deadline_index < len(due) else 1440.0
            hours = max(1 / 60, (deadline - current_minutes) / 60)
            grid_energy = (
                (battery.soc_max - battery.soc) * battery.capacity_kwh / battery.charging_efficiency
            )
            requested = min(power_kw, grid_energy / hours)
        allocated = min(requested, remaining)
        if allocated > 1e-9:
            allocation.append((battery, allocated))
            remaining -= allocated
    return allocation
