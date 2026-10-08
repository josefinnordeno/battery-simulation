from __future__ import annotations

import math
from dataclasses import dataclass, field
from numbers import Integral
from pathlib import Path

import numpy as np

from charging import allocate_charging
from data_loader import background_load, create_schedule, load_machine_rows, time_labels
from duty_cycle import DutyCycle
from models import Battery, Machine


REFERENCE_CHARGER_COUNT = 22
REFERENCE_EFFICIENCY = 0.92
REFERENCE_SWAP_MINUTES = 25
REFERENCE_SITE_LOAD_KW = 250.0


@dataclass
class SimulationResult:
    labels: list[str]
    machines: list[Machine]
    soc_history: dict[int, list[float]]
    background_kw: list[float]
    charging_kw: list[float]
    total_kw: list[float]
    swaps: list[dict]
    active_machine_count: list[int]
    charging_battery_count: list[int] = field(default_factory=list)
    reserve_count: list[int] = field(default_factory=list)
    stored_charging_energy_kwh: float = 0.0
    grid_charging_energy_kwh: float = 0.0
    unreplenished_grid_energy_kwh: float = 0.0
    charging_efficiency: float = REFERENCE_EFFICIENCY
    charger_count: int = REFERENCE_CHARGER_COUNT
    swap_downtime_minutes: float = 0.0
    downtime_minutes: float = 0.0
    reserve_shortage_minutes: float = 0.0
    reserve_shortage_events: int = 0
    unmet_energy_kwh: float = 0.0
    delivered_energy_kwh: float = 0.0
    peak_charging_kw: float = 0.0
    peak_total_kw: float = 0.0
    peak_requested_total_kw: float = 0.0
    charging_curtailment_minutes: int = 0
    curtailed_charging_energy_kwh: float = 0.0
    requested_grid_exceedance_minutes: int = 0
    grid_exceedance_minutes: int = 0
    batteries: list[Battery] = field(default_factory=list)
    inventory_history: list[dict[str, int]] = field(default_factory=list)

    @property
    def kpis(self) -> dict:
        return {
            "swaps": len(self.swaps),
            "max_simultaneous_charging": max(self.charging_battery_count, default=0),
            "peak_charging_kw": self.peak_charging_kw,
            "peak_total_kw": self.peak_total_kw,
            "minimum_reserve": min(self.reserve_count, default=0),
            "downtime_minutes": self.downtime_minutes,
            "reserve_shortage_minutes": self.reserve_shortage_minutes,
            "unmet_energy_kwh": self.unmet_energy_kwh,
        }


def _predicted_deadlines(machines: list[Machine], minute: int) -> list[float]:
    """Forecast shared-module demand from scheduled mean load, not future noise."""
    deadlines = []
    for machine in machines:
        remaining = (machine.battery.soc - machine.battery.soc_min) * machine.battery.capacity_kwh
        usable = (machine.battery.soc_max - machine.battery.soc_min) * machine.battery.capacity_kwh
        for step in range(minute // 15, 96):
            start = max(float(minute), step * 15.0, machine.busy_until_minutes)
            end = step * 15.0 + machine.schedule[step] * 15
            if end <= start:
                continue
            energy = machine.average_power_kw * (end - start) / 60
            # No replacement is needed exactly at the end of the final job.
            while remaining < energy - 1e-9:
                deadline = start + remaining / machine.average_power_kw * 60
                deadlines.append(deadline)
                start = deadline
                energy -= remaining
                remaining = usable
            remaining -= energy
    return sorted(deadlines)


def run_simulation(
    capacity_kwh: float = 140.0,
    charging_power_kw: float = 22.0,
    swap_time_minutes: int = REFERENCE_SWAP_MINUTES,
    scenario: str = "high",
    reserve_count: int = 25,
    seed: int = 42,
    *,
    operator_count: int | None = None,
    charger_count: int = REFERENCE_CHARGER_COUNT,
    grid_limit_kw: float = 1000.0,
    charging_efficiency: float = REFERENCE_EFFICIENCY,
    soc_min: float = 0.1,
    soc_max: float = 0.8,
    charging_policy: str = "immediate",
    reserve_target: int = 3,
    duty_cycle: DutyCycle | None = None,
    site_load_kw: float | list[float] | None = None,
    csv_path: str | Path | None = None,
) -> SimulationResult:
    """Simulate physical inventory on one-minute substeps; output 15-minute bins.

    Defaults are deterministic and include the entire selected CSV fleet. The
    capacity argument overrides OEM/CSV capacities for every interchangeable
    module. reserve_count counts *spares*, not modules installed in machines.
    Swaps start only on depleted scheduled machines, require a charged spare,
    and return the removed module to charging after swap_time_minutes.
    """
    for name, value in (
        ("capacity_kwh", capacity_kwh),
        ("charging_power_kw", charging_power_kw),
        ("grid_limit_kw", grid_limit_kw),
    ):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    for name, value in (
        ("swap_time_minutes", swap_time_minutes),
        ("reserve_count", reserve_count),
        ("charger_count", charger_count),
        ("reserve_target", reserve_target),
    ):
        if not isinstance(value, Integral) or value < 0:
            raise ValueError(f"{name} must be a non-negative integer")
    if operator_count is not None and (
        not isinstance(operator_count, Integral) or operator_count < 0
    ):
        raise ValueError("operator_count must be a non-negative integer or None")
    if scenario not in {"high", "low"}:
        raise ValueError("scenario must be 'high' or 'low'")
    if charging_policy not in {"immediate", "deadline"}:
        raise ValueError("charging_policy must be 'immediate' or 'deadline'")

    rows = load_machine_rows(csv_path)
    machines = []
    for index, row in enumerate(rows):
        daily_hours = row[f"{scenario}_daily_hours"]
        schedule = create_schedule(daily_hours, scenario)
        if operator_count is not None and index >= operator_count:
            schedule = [0.0] * 96
        battery = Battery(
            index, capacity_kwh, soc_max, "in_use", soc_min, soc_max, charging_efficiency
        )
        machines.append(
            Machine(
                row["name"], row["type"], daily_hours, row["average_power_kw"], battery, schedule
            )
        )
    reserve = [
        Battery(
            len(rows) + i, capacity_kwh, soc_max, "reserve", soc_min, soc_max, charging_efficiency
        )
        for i in range(reserve_count)
    ]
    batteries = [machine.battery for machine in machines] + reserve.copy()
    rng = np.random.default_rng(seed)
    profiles = [
        duty_cycle.profile(machine.schedule, rng) if duty_cycle else [1.0] * 96
        for machine in machines
    ]
    if site_load_kw is None:
        background = (
            [REFERENCE_SITE_LOAD_KW] * 96
            if scenario == "high"
            else background_load(scenario).tolist()
        )
    elif isinstance(site_load_kw, (int, float)):
        background = [float(site_load_kw)] * 96
    else:
        background = list(site_load_kw)
    if len(background) != 96 or any(not math.isfinite(value) or value < 0 for value in background):
        raise ValueError("site_load_kw must be a non-negative finite scalar or 96-value series")
    result = SimulationResult(
        time_labels(),
        machines,
        {i: [] for i in range(len(machines))},
        background,
        [0.0] * 96,
        [0.0] * 96,
        [],
        [0] * 96,
        [0] * 96,
        [reserve_count] * 96,
        charging_efficiency=charging_efficiency,
        charger_count=charger_count,
        batteries=batteries,
    )
    pending: list[tuple[Battery, float]] = []
    charging: list[Battery] = []
    short_machines: set[int] = set()

    for minute in range(1440):
        step = minute // 15
        offset = minute % 15
        active_count = 0
        for index, machine in enumerate(machines):
            scheduled = max(0.0, min(1.0, machine.schedule[step] * 15 - offset))
            if not scheduled:
                continue
            if machine.battery.soc <= soc_min + 1e-9 and minute >= machine.busy_until_minutes:
                if reserve:
                    returned = machine.attach(reserve.pop(0))
                    returned.state = "waiting"
                    machine.mark_swap(minute, swap_time_minutes)
                    pending.append((returned, machine.busy_until_minutes))
                    result.swaps.append(
                        {
                            "step": step,
                            "time": f"{minute // 60:02d}:{minute % 60:02d}",
                            "machine_index": index,
                            "machine": machine.name,
                            "duration_minutes": swap_time_minutes,
                            "reason": "depleted",
                        }
                    )
                    short_machines.discard(index)
                else:
                    if index not in short_machines:
                        result.reserve_shortage_events += 1
                        short_machines.add(index)
                    machine.shortage_minutes += scheduled
            power = machine.average_power_kw * profiles[index][step]
            consumed = 0.0
            if minute >= machine.busy_until_minutes:
                consumed = machine.battery.consume(power * scheduled / 60)
                if consumed > 0:
                    active_count += 1
            worked_minutes = consumed / power * 60 if power > 0 else 0.0
            machine.downtime_minutes += max(0.0, scheduled - worked_minutes)
            machine.delivered_energy_kwh += consumed
            result.unmet_energy_kwh += max(0.0, power * scheduled / 60 - consumed)
        if offset == 0:
            result.active_machine_count[step] = active_count
        result.reserve_count[step] = min(result.reserve_count[step], len(reserve))

        for battery, available_at in pending:
            if available_at <= minute:
                charging.append(battery)
        pending = [(battery, ready) for battery, ready in pending if ready > minute]
        deadlines = (
            _predicted_deadlines(machines, minute)
            if charging and charging_policy == "deadline"
            else None
        )
        dispatch_options: dict = {
            "policy": charging_policy,
            "deadlines": deadlines,
            "current_minutes": minute,
            "reserve_count": len(reserve),
            "reserve_target": reserve_target,
        }
        requested_allocation = allocate_charging(
            charging, charger_count, charging_power_kw, math.inf, **dispatch_options
        )
        requested_grid_energy = sum(
            min(
                power / 60,
                (battery.soc_max - battery.soc)
                * battery.capacity_kwh
                / battery.charging_efficiency,
            )
            for battery, power in requested_allocation
        )
        allocation = allocate_charging(
            charging,
            charger_count,
            charging_power_kw,
            grid_limit_kw - background[step],
            **dispatch_options,
        )
        grid_energy = 0.0
        for battery, power in allocation:
            stored = battery.charge(power, 1 / 60)
            result.stored_charging_energy_kwh += stored
            grid_energy += battery.last_grid_energy_kwh
            if battery.state == "full":
                charging.remove(battery)
                battery.state = "reserve"
                reserve.append(battery)
        minute_power = grid_energy * 60
        result.grid_charging_energy_kwh += grid_energy
        result.charging_kw[step] += grid_energy / 0.25
        result.charging_battery_count[step] = max(
            result.charging_battery_count[step], len(allocation)
        )
        result.reserve_count[step] = min(result.reserve_count[step], len(reserve))
        result.peak_charging_kw = max(result.peak_charging_kw, minute_power)
        result.peak_total_kw = max(result.peak_total_kw, background[step] + minute_power)
        requested_total_kw = background[step] + requested_grid_energy * 60
        result.peak_requested_total_kw = max(result.peak_requested_total_kw, requested_total_kw)
        curtailment = max(0.0, requested_grid_energy - grid_energy)
        result.curtailed_charging_energy_kwh += curtailment
        if curtailment > 1e-9:
            result.charging_curtailment_minutes += 1
        if requested_total_kw > grid_limit_kw + 1e-6:
            result.requested_grid_exceedance_minutes += 1
        if background[step] + minute_power > grid_limit_kw + 1e-6:
            result.grid_exceedance_minutes += 1
        if offset == 14:
            for index, machine in enumerate(machines):
                result.soc_history[index].append(machine.battery.soc * 100)
            result.inventory_history.append(
                {
                    "in_use": len(machines),
                    "reserve": len(reserve),
                    "waiting": len(pending),
                    "charging": len(charging),
                }
            )

    result.total_kw = [base + charge for base, charge in zip(background, result.charging_kw)]
    result.swap_downtime_minutes = sum(machine.swap_downtime_minutes for machine in machines)
    result.downtime_minutes = sum(machine.downtime_minutes for machine in machines)
    result.reserve_shortage_minutes = sum(machine.shortage_minutes for machine in machines)
    result.delivered_energy_kwh = sum(machine.delivered_energy_kwh for machine in machines)
    result.unreplenished_grid_energy_kwh = sum(
        max(0.0, battery.soc_max - battery.soc) * battery.capacity_kwh / battery.charging_efficiency
        for battery in batteries
    )
    return result
