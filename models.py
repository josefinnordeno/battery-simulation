from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Battery:
    """Battery state using the reference 10% to 80% operating window."""

    battery_id: int
    capacity_kwh: float
    soc: float = 0.8
    state: str = "reserve"

    def charge(self, power_kw: float, hours: float, efficiency: float = 0.92, soc_max: float = 0.8) -> float:
        if self.soc >= soc_max or power_kw <= 0 or efficiency <= 0:
            return 0.0
        energy = min(power_kw * efficiency * hours, (soc_max - self.soc) * self.capacity_kwh)
        self.soc += energy / self.capacity_kwh
        if self.soc >= soc_max - 1e-9:
            self.soc = soc_max
            self.state = "full"
        else:
            self.state = "charging"
        return energy

    def consume(self, energy_kwh: float) -> float:
        consumed = min(max(energy_kwh, 0.0), self.soc * self.capacity_kwh)
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
    schedule: list[bool] = field(default_factory=list)
    swap_count: int = 0
    swap_remaining_minutes: float = 0.0
    remaining_work_steps: int = 0

    def consume_for_step(self, hours: float, rng) -> float:
        if self.remaining_work_steps <= 0:
            return 0.0
        demand = self.average_power_kw
        self.battery.consume(demand * hours)
        self.remaining_work_steps -= 1
        return demand

    def attach(self, battery: Battery, swap_time_minutes: float = 25.0) -> Battery:
        old_battery = self.battery
        old_battery.state = "charging"
        self.battery = battery
        battery.state = "in_use"
        self.swap_count += 1
        self.swap_remaining_minutes = swap_time_minutes
        return old_battery
