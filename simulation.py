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


def run_simulation(
    capacity_kwh: float = 140.0,
    charging_power_kw: float = 22.0,
    swap_time_minutes: int = 15,
    scenario: str = "high",
    reserve_count: int = 25,
    seed: int = 42,
) -> SimulationResult:
    rng = np.random.default_rng(seed)
    rows = load_machine_rows()
    machines = [
        Machine(
            row["name"],
            row["type"],
            row["annual_hours"],
            row["average_power_kw"],
            Battery(index, row.get("battery_capacity_kwh", capacity_kwh), 0.8, "in_use"),
            create_schedule(row["annual_hours"], scenario, rng),
        )
        for index, row in enumerate(rows)
    ]
    reserve = [Battery(1000 + i, capacity_kwh, 0.8, "reserve") for i in range(reserve_count)]
    charging = []
    labels = time_labels()
    soc_history = {index: [] for index, _ in enumerate(machines)}
    background = background_load(scenario)
    charging_kw_history, total_kw_history, active_counts = [], [], []
    swaps = []
    hours_per_step = 0.25

    for step, label in enumerate(labels):
        active_kw = 0.0
        for machine_index, machine in enumerate(machines):
            active_kw += machine.consume_for_step(hours_per_step, rng)
            hour = step / 4.0
            break_time = (9.0 <= hour <= 9.25) or (11.5 <= hour <= 12.5) or (14.5 <= hour <= 14.75)
            should_swap = machine.battery.soc < 0.10 or (break_time and machine.battery.soc < 0.50 and rng.random() < 0.85)
            if should_swap and reserve:
                returned = machine.attach(reserve.pop(0))
                charging.append(returned)
                swaps.append({"time": label, "machine": machine.name, "reason": "low SoC or break"})
            soc_history[machine_index].append(machine.battery.soc * 100.0)

        charged_this_step = 0.0
        still_charging = []
        for battery in charging:
            power = charging_power_kw
            charged_this_step += battery.charge(power, hours_per_step) / hours_per_step
            if battery.soc >= 1.0:
                reserve.append(battery)
            else:
                still_charging.append(battery)
        charging = still_charging
        charging_kw_history.append(charged_this_step)
        total_kw_history.append(background[step] + charged_this_step)
        active_counts.append(sum(bool(machine.schedule[0]) for machine in machines if machine.schedule))

    return SimulationResult(labels, machines, soc_history, background.tolist(), charging_kw_history, total_kw_history, swaps, active_counts)
