"""Reproducible Monte Carlo days and infrastructure sensitivity comparisons."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import asdict, dataclass
from numbers import Integral

import numpy as np

from data_loader import load_machine_rows
from duty_cycle import DutyCycle
from simulation import run_simulation


def run_monte_carlo(days: int = 500, seed: int = 42, **simulation_options) -> dict:
    """Summarize independent, seeded days using an explicitly assumed duty cycle."""
    if not isinstance(days, Integral) or days < 1:
        raise ValueError("days must be a positive integer")
    options = dict(simulation_options)
    options.setdefault("duty_cycle", DutyCycle())
    seeds = np.random.SeedSequence(seed).spawn(days)
    peaks, requested_peaks, energies, terminal_energies, downtimes, swap_downtimes = (
        [],
        [],
        [],
        [],
        [],
        [],
    )
    shortage_days = grid_days = downtime_days = 0
    requested_grid_days = curtailment_days = 0
    curtailed_energies = []
    for child in seeds:
        result = run_simulation(seed=int(child.generate_state(1)[0]), **options)
        peaks.append(result.peak_total_kw)
        requested_peaks.append(result.peak_requested_total_kw)
        energies.append(result.grid_charging_energy_kwh)
        terminal_energies.append(result.unreplenished_grid_energy_kwh)
        downtimes.append(result.downtime_minutes)
        swap_downtimes.append(result.swap_downtime_minutes)
        curtailed_energies.append(result.curtailed_charging_energy_kwh)
        shortage_days += result.reserve_shortage_events > 0
        grid_days += result.grid_exceedance_minutes > 0
        requested_grid_days += result.requested_grid_exceedance_minutes > 0
        curtailment_days += result.charging_curtailment_minutes > 0
        downtime_days += any(machine.downtime_minutes > 30 for machine in result.machines)
    return {
        "days": days,
        "seed": seed,
        "peak_total_kw": dict(
            zip(("p50", "p95", "p99"), map(float, np.percentile(peaks, [50, 95, 99])))
        ),
        "probability_reserve_shortage": shortage_days / days,
        "probability_grid_exceedance": grid_days / days,
        "requested_peak_total_kw": dict(
            zip(("p50", "p95", "p99"), map(float, np.percentile(requested_peaks, [50, 95, 99])))
        ),
        "probability_requested_grid_exceedance": requested_grid_days / days,
        "probability_charging_curtailment": curtailment_days / days,
        "mean_curtailed_charging_energy_kwh": float(np.mean(curtailed_energies)),
        "probability_machine_downtime_over_30_minutes": downtime_days / days,
        "mean_grid_charging_energy_kwh": float(np.mean(energies)),
        "mean_unreplenished_grid_energy_kwh": float(np.mean(terminal_energies)),
        "mean_downtime_minutes": float(np.mean(downtimes)),
        "mean_swap_downtime_minutes": float(np.mean(swap_downtimes)),
    }


@dataclass(frozen=True)
class Infrastructure:
    capacity_kwh: float
    pool_size: int
    charging_power_kw: float
    scenario: str = "high"
    charger_count: int = 22


DEFAULT_CONFIGURATIONS = (
    Infrastructure(70, 60, 22),
    Infrastructure(100, 45, 22),
    Infrastructure(140, 40, 22),
    Infrastructure(200, 30, 22),
    Infrastructure(140, 40, 50),
    Infrastructure(140, 40, 100),
)


@dataclass(frozen=True)
class CostAssumptions:
    """User-supplied rates in one consistent currency; no invented defaults."""

    module_capital_per_kwh: float
    charger_capital_per_kw: float
    capital_daily_factor: float
    energy_per_kwh: float
    peak_per_kw_day: float
    downtime_per_machine_hour: float

    def __post_init__(self) -> None:
        if any(not math.isfinite(value) or value < 0 for value in asdict(self).values()):
            raise ValueError("Cost assumptions must be finite and non-negative")

    def daily_cost(self, config: Infrastructure, summary: dict) -> float:
        capital = config.capacity_kwh * config.pool_size * self.module_capital_per_kwh
        capital += config.charger_count * config.charging_power_kw * self.charger_capital_per_kw
        # Peak tariff is deliberately based on a chosen conservative P95 design day.
        return (
            capital * self.capital_daily_factor
            + (
                summary["mean_grid_charging_energy_kwh"]
                + summary["mean_unreplenished_grid_energy_kwh"]
            )
            * self.energy_per_kwh
            + summary["peak_total_kw"]["p95"] * self.peak_per_kw_day
            + summary["mean_downtime_minutes"] / 60 * self.downtime_per_machine_hour
        )


def run_sensitivity(
    configurations=DEFAULT_CONFIGURATIONS,
    *,
    days: int = 500,
    seed: int = 42,
    costs: CostAssumptions | None = None,
    shortage_probability_limit: float = 0.01,
    **simulation_options,
) -> dict:
    """Compare configurations on common random days; rank only supplied costs.

    Feasibility means P(any reserve shortage) < limit. Planned swaps are included
    in downtime cost, but excluded from this shortage reliability constraint.
    """
    if not 0 < shortage_probability_limit <= 1:
        raise ValueError("shortage_probability_limit must be in (0, 1]")
    fleet_size = len(load_machine_rows(simulation_options.get("csv_path")))
    comparisons = []
    for config in configurations:
        if not isinstance(config.pool_size, Integral) or config.pool_size < fleet_size:
            raise ValueError("pool_size must include a battery for every fleet machine")
        summary = run_monte_carlo(
            days,
            seed,
            capacity_kwh=config.capacity_kwh,
            reserve_count=config.pool_size - fleet_size,
            charging_power_kw=config.charging_power_kw,
            scenario=config.scenario,
            charger_count=config.charger_count,
            **simulation_options,
        )
        comparisons.append(
            {
                "configuration": asdict(config),
                "summary": summary,
                "feasible": summary["probability_reserve_shortage"] < shortage_probability_limit,
                "daily_cost": costs.daily_cost(config, summary) if costs else None,
            }
        )
    candidates = [row for row in comparisons if row["feasible"] and row["daily_cost"] is not None]
    best = min(candidates, key=lambda row: row["daily_cost"]) if candidates else None
    return {
        "comparisons": comparisons,
        "best_configuration": best["configuration"] if best else None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--policy", choices=("immediate", "deadline"), default="immediate")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    function = run_sensitivity if args.sweep else run_monte_carlo
    print(
        json.dumps(function(days=args.days, seed=args.seed, charging_policy=args.policy), indent=2)
    )


if __name__ == "__main__":
    main()
