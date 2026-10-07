from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Battery:
    """Battery state with a CC/CV charging curve."""

    battery_id: int
    capacity_kwh: float
    soc: float = 1.0
    state: str = "reserve"

    def charge(self, power_kw: float, hours: float) -> float:
        if self.soc >= 1.0 or power_kw <= 0:
            return 0.0
        acceptance = power_kw if self.soc < 0.8 else power_kw * max(0.0, (1.0 - self.soc) / 0.2)
        energy = min(acceptance * hours, (1.0 - self.soc) * self.capacity_kwh)
        self.soc += energy / self.capacity_kwh
        if self.soc >= 0.999999:
            self.soc = 1.0
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

    def consume_for_step(self, hours: float, rng) -> float:
        if not self.schedule:
            return 0.0
        active = self.schedule.pop(0)
        if not active:
            return 0.0
        demand = max(0.0, rng.normal(self.average_power_kw, self.average_power_kw * 0.12))
        self.battery.consume(demand * hours)
        return demand

    def attach(self, battery: Battery) -> Battery:
        old_battery = self.battery
        old_battery.state = "charging"
        self.battery = battery
        battery.state = "in_use"
        self.swap_count += 1
        return old_battery
