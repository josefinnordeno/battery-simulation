from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from data_loader import background_load, create_schedule, load_machine_rows, time_labels
from models import Battery, Machine


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
    charging_energy_kwh: list[float]
    grid_energy_kwh: list[float]
    swap_downtime_minutes: float
    max_simultaneously_charging: int
    peak_charging_load_kw: float
    peak_total_site_load_kw: float
    minimum_available_charged_reserve: int
    charging_efficiency: float


def run_simulation(
    capacity_kwh: float = 140.0,
    charging_power_kw: float = 22.0,
    swap_time_minutes: int = 25,
    scenario: str = "high",
    reserve_count: int = 25,
    seed: int = 42,
    charging_positions: int | None = None,
) -> SimulationResult:
    charging_efficiency = 0.92
    rng = np.random.default_rng(seed)
    rows = load_machine_rows()
    machines = [
        Machine(
            row["name"],
            row["type"],
            row["annual_hours"],
            row["average_power_kw"],
            Battery(index, capacity_kwh, 0.8, "in_use"),
            create_schedule(row["annual_hours"], scenario, rng, row.get("machine_class", "A")),
        )
        for index, row in enumerate(rows)
    ]
    for machine in machines:
        machine.remaining_work_steps = sum(machine.schedule)
    reserve = [Battery(1000 + i, capacity_kwh, 0.8, "reserve") for i in range(reserve_count)]
    charging = []
    if charging_positions is None:
        charging_positions = len(machines) + reserve_count
    labels = time_labels()
    soc_history = {index: [] for index, _ in enumerate(machines)}
    background = background_load(scenario)
    charging_kw_history, total_kw_history, active_counts = [], [], []
    charging_energy_history = []
    grid_energy_history = []
    swaps = []
    swap_downtime_minutes = 0.0
    max_charging = 0
    minimum_reserve = reserve_count
    hours_per_step = 0.25

    for step, label in enumerate(labels):
        active_kw = 0.0
        for machine_index, machine in enumerate(machines):
            if machine.swap_remaining_minutes > 0:
                machine.swap_remaining_minutes = max(0.0, machine.swap_remaining_minutes - 60.0 * hours_per_step)
            elif step >= 32:
                active_kw += machine.consume_for_step(hours_per_step, rng)
            should_swap = machine.swap_remaining_minutes <= 0 and machine.battery.soc <= 0.10
            if should_swap and reserve:
                returned = machine.attach(reserve.pop(0), swap_time_minutes)
                charging.append(returned)
                swap_downtime_minutes += swap_time_minutes
                swaps.append({"time": label, "machine": machine.name, "reason": "minimum SoC", "duration_minutes": swap_time_minutes})
            soc_history[machine_index].append(machine.battery.soc * 100.0)

        charged_this_step = 0.0
        stored_energy_this_step = 0.0
        still_charging = []
        active_charging = min(len(charging), charging_positions)
        max_charging = max(max_charging, active_charging)
        for battery in charging[:charging_positions]:
            power = charging_power_kw
            stored_energy = battery.charge(power, hours_per_step, charging_efficiency)
            stored_energy_this_step += stored_energy
            charged_this_step += stored_energy / charging_efficiency / hours_per_step
            if battery.soc >= 0.8:
                reserve.append(battery)
            else:
                still_charging.append(battery)
        still_charging.extend(charging[charging_positions:])
        charging = still_charging
        minimum_reserve = min(minimum_reserve, len(reserve))
        charging_kw_history.append(active_charging * charging_power_kw)
        charging_energy_history.append(stored_energy_this_step)
        grid_energy_history.append(stored_energy_this_step / charging_efficiency)
        total_kw_history.append(background[step] + charging_kw_history[-1])
        active_counts.append(sum(machine.remaining_work_steps > 0 and machine.swap_remaining_minutes <= 0 for machine in machines))

    return SimulationResult(
        labels, machines, soc_history, background.tolist(), charging_kw_history, total_kw_history,
        swaps, active_counts, charging_energy_history, grid_energy_history, swap_downtime_minutes, max_charging,
        max_charging * charging_power_kw,
        max(total_kw_history, default=0.0),
        minimum_reserve, charging_efficiency,
    )
