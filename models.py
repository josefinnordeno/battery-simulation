from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass
class Battery:
    """Battery state using the reference operating window and efficiency."""

    battery_id: int
    capacity_kwh: float
    soc: float = 0.8
    state: str = "reserve"
    soc_min: float = 0.1
    soc_max: float = 0.8
    charging_efficiency: float = 0.92
    last_grid_energy_kwh: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.capacity_kwh) or self.capacity_kwh <= 0:
            raise ValueError("Battery capacity must be finite and positive")
        if not 0 <= self.soc_min < self.soc_max <= 1:
            raise ValueError("Battery requires 0 <= soc_min < soc_max <= 1")
        if not self.soc_min <= self.soc <= self.soc_max:
            raise ValueError("Initial SoC must be within the operating window")
        if not 0 < self.charging_efficiency <= 1:
            raise ValueError("Charging efficiency must be in (0, 1]")

    def charge(self, power_kw: float, hours: float) -> float:
        self.last_grid_energy_kwh = 0.0
        if self.soc >= self.soc_max or power_kw <= 0 or hours <= 0:
            return 0.0
        energy = min(
            power_kw * hours * self.charging_efficiency,
            (self.soc_max - self.soc) * self.capacity_kwh,
        )
        self.soc += energy / self.capacity_kwh
        self.last_grid_energy_kwh = energy / self.charging_efficiency
        if self.soc >= self.soc_max - 1e-9:
            self.soc = self.soc_max
            self.state = "full"
        else:
            self.state = "charging"
        return energy

    def consume(self, energy_kwh: float) -> float:
        available = max(0.0, self.soc - self.soc_min) * self.capacity_kwh
        consumed = min(max(energy_kwh, 0.0), available)
        self.soc -= consumed / self.capacity_kwh
        self.state = "in_use"
        return consumed


@dataclass
class Machine:
    name: str
    machine_type: str
    operating_hours: float
    average_power_kw: float
    battery: Battery
    schedule: list[float] = field(default_factory=list)
    swap_count: int = 0
    swap_downtime_minutes: int = 0
    busy_until_minutes: float = 0.0
    downtime_minutes: float = 0.0
    shortage_minutes: float = 0.0
    delivered_energy_kwh: float = 0.0

    def consume_for_step(self, hours: float, rng=None) -> float:
        """Consume deterministic mean demand; retain the legacy rng argument."""
        if not self.schedule:
            return 0.0
        active = self.schedule.pop(0)
        if not active:
            return 0.0
        consumed = self.battery.consume(self.average_power_kw * hours * active)
        return consumed / hours if hours > 0 else 0.0

    def attach(self, battery: Battery) -> Battery:
        old_battery = self.battery
        old_battery.state = "charging"
        self.battery = battery
        battery.state = "in_use"
        self.swap_count += 1
        return old_battery

    def mark_swap(self, start_minutes: float, duration_minutes: int) -> None:
        self.busy_until_minutes = max(self.busy_until_minutes, start_minutes + duration_minutes)
        self.swap_downtime_minutes += duration_minutes
