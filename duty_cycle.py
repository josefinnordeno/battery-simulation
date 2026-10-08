"""Illustrative correlated workloads; replace assumptions with telemetry later."""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class DutyCycle:
    states: tuple[str, ...] = ("idle", "light_work", "normal_work", "heavy_work", "travel")
    multipliers: tuple[float, ...] = (0.15, 0.65, 1.0, 1.6, 1.2)
    probabilities: tuple[float, ...] = (0.15, 0.2, 0.35, 0.2, 0.1)
    persistence: float = 0.8

    def __post_init__(self) -> None:
        if (
            not self.states
            or len(self.states) != len(self.multipliers)
            or len(self.states) != len(self.probabilities)
        ):
            raise ValueError("Duty-cycle states, multipliers and probabilities must align")
        if any(not np.isfinite(v) or v <= 0 for v in self.multipliers):
            raise ValueError("Duty-cycle multipliers must be finite and positive")
        if any(not np.isfinite(v) or v < 0 for v in self.probabilities) or not np.isclose(
            sum(self.probabilities), 1
        ):
            raise ValueError("Duty-cycle probabilities must sum to one")
        if not 0 <= self.persistence <= 1:
            raise ValueError("Duty-cycle persistence must be in [0, 1]")

    def profile(self, schedule: list[float], rng: np.random.Generator) -> list[float]:
        """Correlate adjacent active quarters; normalize planned daily mean to 1."""
        state = int(rng.choice(len(self.states), p=self.probabilities))
        values = []
        for active in schedule:
            if active and rng.random() >= self.persistence:
                state = int(rng.choice(len(self.states), p=self.probabilities))
            values.append(self.multipliers[state] if active else 0.0)
        hours = sum(schedule)
        weighted_sum = sum(value * active for value, active in zip(values, schedule))
        scale = hours / weighted_sum if weighted_sum else 1.0
        return [value * scale for value in values]
